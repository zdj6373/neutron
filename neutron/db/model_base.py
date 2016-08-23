# Copyright (c) 2012 OpenStack Foundation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import debtcollector
from oslo_db.sqlalchemy import models
from oslo_utils import uuidutils
import sqlalchemy as sa
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext import declarative
from sqlalchemy import orm

from neutron.api.v2 import attributes as attr


class HasProject(object):
    """Project mixin, add to subclasses that have a user."""

    # NOTE(jkoelker) project_id is just a free form string ;(
    project_id = sa.Column(sa.String(attr.TENANT_ID_MAX_LEN), index=True)

    def get_tenant_id(self):
        return self.project_id

    def set_tenant_id(self, value):
        self.project_id = value

    @declarative.declared_attr
    def tenant_id(cls):
        return orm.synonym(
            'project_id',
            descriptor=property(cls.get_tenant_id, cls.set_tenant_id))


HasTenant = debtcollector.moves.moved_class(HasProject, "HasTenant", __name__)


class HasProjectNoIndex(HasProject):
    """Project mixin, add to subclasses that have a user."""

    # NOTE(jkoelker) project_id is just a free form string ;(
    project_id = sa.Column(sa.String(attr.TENANT_ID_MAX_LEN))


class HasProjectPrimaryKeyIndex(HasProject):
    """Project mixin, add to subclasses that have a user."""

    # NOTE(jkoelker) project_id is just a free form string ;(
    project_id = sa.Column(sa.String(attr.TENANT_ID_MAX_LEN), nullable=False,
                           primary_key=True, index=True)


class HasProjectPrimaryKey(HasProject):
    """Project mixin, add to subclasses that have a user."""

    # NOTE(jkoelker) project_id is just a free form string ;(
    project_id = sa.Column(sa.String(attr.TENANT_ID_MAX_LEN), nullable=False,
                           primary_key=True)


class HasId(object):
    """id mixin, add to subclasses that have an id."""

    def __init__(self, *args, **kwargs):
        # NOTE(dasm): debtcollector requires init in class
        super(HasId, self).__init__(*args, **kwargs)

    id = sa.Column(sa.String(36),
                   primary_key=True,
                   default=uuidutils.generate_uuid)


class HasStatusDescription(object):
    """Status with description mixin."""

    def __init__(self, *args, **kwargs):
        # NOTE(dasm): debtcollector requires init in class
        super(HasStatusDescription, self).__init__(*args, **kwargs)

    status = sa.Column(sa.String(16), nullable=False)
    status_description = sa.Column(sa.String(attr.DESCRIPTION_MAX_LEN))


class NeutronBase(models.ModelBase):
    """Base class for Neutron Models."""

    __table_args__ = {'mysql_engine': 'InnoDB'}

    def __iter__(self):
        self._i = iter(orm.object_mapper(self).columns)
        return self

    def next(self):
        n = next(self._i).name
        return n, getattr(self, n)

    __next__ = next

    def __repr__(self):
        """sqlalchemy based automatic __repr__ method."""
        items = ['%s=%r' % (col.name, getattr(self, col.name))
                 for col in self.__table__.columns]
        return "<%s.%s[object at %x] {%s}>" % (self.__class__.__module__,
                                               self.__class__.__name__,
                                               id(self), ', '.join(items))


class NeutronBaseV2(NeutronBase):

    @declarative.declared_attr
    def __tablename__(cls):
        # NOTE(jkoelker) use the pluralized name of the class as the table
        return cls.__name__.lower() + 's'


BASEV2 = declarative.declarative_base(cls=NeutronBaseV2)


class StandardAttribute(BASEV2, models.TimestampMixin):
    """Common table to associate all Neutron API resources.

    By having Neutron objects related to this table, we can associate new
    tables that apply to many Neutron objects (e.g. timestamps, rbac entries)
    to this table to avoid schema duplication while maintaining referential
    integrity.

    NOTE(kevinbenton): This table should not have more columns added to it
    unless we are absolutely certain the new column will have a value for
    every single type of Neutron resource. Otherwise this table will be filled
    with NULL entries for combinations that don't make sense. Additionally,
    by keeping this table small we can ensure that performance isn't adversely
    impacted for queries on objects.
    """

    # sqlite doesn't support auto increment on big integers so we use big int
    # for everything but sqlite
    id = sa.Column(sa.BigInteger().with_variant(sa.Integer(), 'sqlite'),
                   primary_key=True, autoincrement=True)

    # NOTE(kevinbenton): this column is redundant information, but it allows
    # operators/devs to look at the contents of this table and know which table
    # the corresponding object is in.
    # 255 was selected as a max just because it's the varchar ceiling in mysql
    # before a 2-byte prefix is required. We shouldn't get anywhere near this
    # limit with our table names...
    resource_type = sa.Column(sa.String(255), nullable=False)
    description = sa.Column(sa.String(attr.DESCRIPTION_MAX_LEN))

    revision_number = sa.Column(
        sa.BigInteger().with_variant(sa.Integer(), 'sqlite'),
        server_default='0', nullable=False)

    __mapper_args__ = {
        # see http://docs.sqlalchemy.org/en/latest/orm/versioning.html for
        # details about how this works
        "version_id_col": revision_number
    }


class HasStandardAttributes(object):
    @declarative.declared_attr
    def standard_attr_id(cls):
        return sa.Column(
            sa.BigInteger().with_variant(sa.Integer(), 'sqlite'),
            sa.ForeignKey(StandardAttribute.id, ondelete="CASCADE"),
            unique=True,
            nullable=False
        )

    # NOTE(kevinbenton): we have to disable the following pylint check because
    # it thinks we are overriding this method in the __init__ method.
    #pylint: disable=method-hidden
    @declarative.declared_attr
    def standard_attr(cls):
        return orm.relationship(StandardAttribute,
                                lazy='joined',
                                cascade='all, delete-orphan',
                                single_parent=True,
                                uselist=False)

    def __init__(self, *args, **kwargs):
        standard_attr_keys = ['description', 'created_at',
                              'updated_at', 'revision_number']
        standard_attr_kwargs = {}
        for key in standard_attr_keys:
            if key in kwargs:
                standard_attr_kwargs[key] = kwargs.pop(key)
        super(HasStandardAttributes, self).__init__(*args, **kwargs)
        # here we automatically create the related standard attribute object
        self.standard_attr = StandardAttribute(
            resource_type=self.__tablename__, **standard_attr_kwargs)

    @declarative.declared_attr
    def description(cls):
        return association_proxy('standard_attr', 'description')

    @declarative.declared_attr
    def created_at(cls):
        return association_proxy('standard_attr', 'created_at')

    @declarative.declared_attr
    def updated_at(cls):
        return association_proxy('standard_attr', 'updated_at')

    def update(self, new_dict):
        # ignore the timestamps if they were passed in. For example, this
        # happens if code calls update_port with modified results of get_port
        new_dict.pop('created_at', None)
        new_dict.pop('updated_at', None)
        super(HasStandardAttributes, self).update(new_dict)

    @declarative.declared_attr
    def revision_number(cls):
        return association_proxy('standard_attr', 'revision_number')

    def bump_revision(self):
        # SQLAlchemy will bump the version for us automatically if the
        # standard attr record is being modified, but we must call this
        # for all other modifications or when relevant children are being
        # modified (e.g. fixed_ips change should bump port revision)
        if self.standard_attr.revision_number is None:
            # this is a brand new object uncommited so we don't bump now
            return
        self.standard_attr.revision_number += 1


def get_unique_keys(model):
    try:
        constraints = model.__table__.constraints
    except AttributeError:
        constraints = []
    return [[c.name for c in constraint.columns]
            for constraint in constraints
            if isinstance(constraint, sa.UniqueConstraint)]
