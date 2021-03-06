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

"""Receiver object."""

from oslo_versionedobjects import base
from oslo_versionedobjects import fields

from senlin.db import api as db_api
from senlin.objects import base as senlin_base


class Receiver(senlin_base.SenlinObject, base.VersionedObjectDictCompat):
    """Senlin receiver object."""

    fields = {
        'id': fields.UUIDField(),
        'name': fields.StringField(),
        'type': fields.StringField(),
        'cluster_id': fields.UUIDField(),
        'actor': fields.DictOfStringsField(nullable=True),
        'action': fields.StringField(),
        'params': fields.DictOfStringsField(nullable=True),
        'channel': fields.DictOfStringsField(nullable=True),
        'created_at': fields.DateTimeField(nullable=True),
        'updated_at': fields.DateTimeField(nullable=True),
        'user': fields.StringField(),
        'project': fields.StringField(),
        'domain': fields.StringField(),
    }

    @staticmethod
    def _from_db_object(context, receiver, db_obj):
        if db_obj is None:
            return None

        for field in receiver.fields:
            receiver[field] = db_obj[field]

        receiver._context = context
        receiver.obj_reset_changes()

        return receiver

    @classmethod
    def create(cls, context, values):
        obj = db_api.receiver_create(context, values)
        return cls._from_db_object(context, cls(context), obj)

    @classmethod
    def get(cls, context, receiver_id, **kwargs):
        obj = db_api.receiver_get(context, receiver_id, **kwargs)
        return cls._from_db_object(context, cls(), obj)

    @classmethod
    def get_by_name(cls, context, name, **kwargs):
        obj = db_api.receiver_get_by_name(context, name, **kwargs)
        return cls._from_db_object(context, cls(), obj)

    @classmethod
    def get_by_short_id(cls, context, short_id, **kwargs):
        obj = db_api.receiver_get_by_short_id(context, short_id, **kwargs)
        return cls._from_db_object(context, cls(), obj)

    @classmethod
    def get_all(cls, context, **kwargs):
        return db_api.receiver_get_all(context, **kwargs)

    @classmethod
    def delete(cls, context, receiver_id):
        db_api.receiver_delete(context, receiver_id)
