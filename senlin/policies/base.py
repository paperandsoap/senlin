# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from oslo_context import context as oslo_context
from oslo_utils import reflection
from oslo_utils import timeutils

from senlin.common import context as senlin_context
from senlin.common import exception
from senlin.common.i18n import _
from senlin.common import schema
from senlin.common import utils
from senlin.engine import environment
from senlin.objects import credential as co
from senlin.objects import policy as po

CHECK_RESULTS = (
    CHECK_OK, CHECK_ERROR,
) = (
    'OK', 'ERROR',
)


class Policy(object):
    '''Base class for policies.'''
    PROFILE_TYPE = 'ANY'

    KEYS = (
        TYPE, VERSION, DESCRIPTION, PROPERTIES,
    ) = (
        'type', 'version', 'description', 'properties',
    )

    spec_schema = {
        TYPE: schema.String(
            _('Name of the policy type.'),
            required=True,
        ),
        VERSION: schema.String(
            _('Version number of the policy type.'),
            required=True,
        ),
        DESCRIPTION: schema.String(
            _('A text description of policy.'),
            default='',
        ),
        PROPERTIES: schema.Map(
            _('Properties for the policy.'),
            required=True,
        )
    }

    properties_schema = {}

    def __new__(cls, name, spec, **kwargs):
        """Create a new policy of the appropriate class.

        :param name: The name for the policy.
        :param spec: A dictionary containing the spec for the policy.
        :param kwargs: Keyword arguments for policy creation.
        :returns: An instance of a specific sub-class of Policy.
        """
        type_name, version = schema.get_spec_version(spec)
        type_str = "-".join([type_name, version])

        if cls != Policy:
            PolicyClass = cls
        else:
            PolicyClass = environment.global_env().get_policy(type_str)

        return super(Policy, cls).__new__(PolicyClass)

    def __init__(self, name, spec, **kwargs):
        """Initialize a policy instance.

        :param name: The name for the policy.
        :param spec: A dictionary containing the detailed policy spec.
        :param kwargs: Keyword arguments for initializing the policy.
        :returns: An instance of a specific sub-class of Policy.
        """

        type_name, version = schema.get_spec_version(spec)
        type_str = "-".join([type_name, version])
        self.name = name
        self.spec = spec

        self.id = kwargs.get('id', None)
        self.type = kwargs.get('type', type_str)
        self.user = kwargs.get('user')
        self.project = kwargs.get('project')
        self.domain = kwargs.get('domain')
        self.data = kwargs.get('data', {})

        self.created_at = kwargs.get('created_at', None)
        self.updated_at = kwargs.get('updated_at', None)

        self.spec_data = schema.Spec(self.spec_schema, spec)
        self.properties = schema.Spec(self.properties_schema,
                                      self.spec.get(self.PROPERTIES, {}))
        self.singleton = True

    @classmethod
    def _from_object(cls, policy):
        """Construct a policy from a Policy object.

        @param cls: The target class.
        @param policy: A policy object.
        """

        kwargs = {
            'id': policy.id,
            'type': policy.type,
            'user': policy.user,
            'project': policy.project,
            'domain': policy.domain,
            'created_at': policy.created_at,
            'updated_at': policy.updated_at,
            'data': policy.data,
        }

        return cls(policy.name, policy.spec, **kwargs)

    @classmethod
    def load(cls, context, policy_id=None, db_policy=None, project_safe=True):
        """Retrieve and reconstruct a policy object from DB.

        :param context: DB context for object retrieval.
        :param policy_id: Optional parameter specifying the ID of policy.
        :param db_policy: Optional parameter referencing a policy DB object.
        :param project_safe: Optional parameter specifying whether only
                             policies belong to the context.project will be
                             loaded.
        :returns: An object of the proper policy class.
        """
        if db_policy is None:
            db_policy = po.Policy.get(context, policy_id,
                                      project_safe=project_safe)
            if db_policy is None:
                raise exception.PolicyNotFound(policy=policy_id)

        return cls._from_object(db_policy)

    @classmethod
    def load_all(cls, context, limit=None, marker=None, sort=None,
                 filters=None, project_safe=True):
        """Retrieve all policies from database."""

        objs = po.Policy.get_all(context, limit=limit, marker=marker,
                                 sort=sort, filters=filters,
                                 project_safe=project_safe)

        for obj in objs:
            yield cls._from_object(obj)

    @classmethod
    def delete(cls, context, policy_id):
        po.Policy.delete(context, policy_id)

    def store(self, context):
        '''Store the policy object into database table.'''
        timestamp = timeutils.utcnow()

        values = {
            'name': self.name,
            'type': self.type,
            'user': self.user,
            'project': self.project,
            'domain': self.domain,
            'spec': self.spec,
            'data': self.data,
        }

        if self.id is not None:
            self.updated_at = timestamp
            values['updated_at'] = timestamp
            po.Policy.update(context, self.id, values)
        else:
            self.created_at = timestamp
            values['created_at'] = timestamp
            policy = po.Policy.create(context, values)
            self.id = policy.id

        return self.id

    def validate(self):
        '''Validate the schema and the data provided.'''
        self.spec_data.validate()
        self.properties.validate()

    @classmethod
    def get_schema(cls):
        return dict((name, dict(schema))
                    for name, schema in cls.properties_schema.items())

    def _build_policy_data(self, data):
        clsname = reflection.get_class_name(self, fully_qualified=False)
        version = self.VERSION
        result = {
            clsname: {
                'version': version,
                'data': data,
            }
        }
        return result

    def _extract_policy_data(self, policy_data):
        clsname = reflection.get_class_name(self, fully_qualified=False)
        if clsname not in policy_data:
            return None
        data = policy_data.get(clsname)
        if 'version' not in data or data['version'] != self.VERSION:
            return None

        return data.get('data', None)

    def attach(self, cluster):
        '''Method to be invoked before policy is attached to a cluster.

        :param cluster: the cluster to which the policy is being attached to.
        :returns: (True, message) if the operation is successful, or (False,
                 error) otherwise.
        '''
        if self.PROFILE_TYPE == ['ANY']:
            return True, None

        profile = cluster.rt['profile']
        if profile.type not in self.PROFILE_TYPE:
            error = _('Policy not applicable on profile type: '
                      '%s') % profile.type
            return False, error

        return True, None

    def detach(self, cluster):
        '''Method to be invoked before policy is detached from a cluster.'''
        return True, None

    def need_check(self, target, action):
        if getattr(self, 'TARGET', None) is None:
            return True

        if (target, action.action) in self.TARGET:
            return True
        else:
            return False

    def pre_op(self, cluster_id, action):
        '''A method that will be invoked before an action execution.'''
        return

    def post_op(self, cluster_id, action):
        '''A method that will be invoked after an action execution.'''
        return

    def to_dict(self):
        pb_dict = {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'user': self.user,
            'project': self.project,
            'domain': self.domain,
            'spec': self.spec,
            'created_at': utils.format_time(self.created_at),
            'updated_at': utils.format_time(self.updated_at),
            'data': self.data,
        }
        return pb_dict

    def _build_conn_params(self, cluster):
        """Build trust-based connection parameters.

        :param cluster: the cluste for which the trust will be checked.
        """
        service_creds = senlin_context.get_service_context()
        params = {
            'username': service_creds.get('username'),
            'password': service_creds.get('password'),
            'auth_url': service_creds.get('auth_url'),
            'user_domain_name': service_creds.get('user_domain_name')
        }

        cred = co.Credential.get(oslo_context.get_current(),
                                 cluster.user, cluster.project)
        if cred is None:
            raise exception.TrustNotFound(trustor=cluster.user)
        params['trust_id'] = cred.cred['openstack']['trust']

        return params
