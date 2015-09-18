# This file is part of Indico.
# Copyright (C) 2002 - 2015 European Organization for Nuclear Research (CERN).
#
# Indico is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# Indico is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Indico; if not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

import json

from collections import OrderedDict
from flask import session, request

from indico.modules.events.registration.controllers.management import RHManageRegFormBase
from indico.modules.events.registration.models.items import RegistrationFormItemType, RegistrationFormItem
from indico.modules.events.registration.views import WPManageRegistration
from indico.modules.events.registration.util import get_registration_field_data, get_user_info
from indico.util.i18n import _
from indico.web.flask.templating import get_template_module
from indico.web.util import jsonify_data

# TODO: Create a better mapping
USER_INFO = OrderedDict({
    'user_id': _('ID'),
    'user_surname': _('Surname'),
    'user_name': _('First name'),
    'user_email': _('Email'),
    'user_position': _('Position'),
    'user_institution': _('Institution'),
    'user_phone': _('Phone'),
    'user_city': _('City'),
    'user_country': _('Country'),
    'user_address': _('Address'),
    'user_paid': _('Paid'),
    'user_payment_id': _('Payment ID'),
    'user_payment_amount': _('Payment amount')
})


class RHRegistrationsListManage(RHManageRegFormBase):
    """List all registrations of a specific registration form of an event"""

    def _process(self):
        visible_columns = session.get('reg_list_columns', {'items': [], 'user_info': []})
        regform_items = RegistrationFormItem.find_all(RegistrationFormItem.id.in_(visible_columns['items']))
        return WPManageRegistration.render_template('management/regform_reglist.html', self.event, regform=self.regform,
                                                    event=self.event, visible_cols_regform_items=regform_items,
                                                    visible_cols_user_info=visible_columns['user_info'],
                                                    get_registration_field_data=get_registration_field_data,
                                                    user_info=USER_INFO, get_user_info=get_user_info)


class RHRegistrationsListCustomize(RHManageRegFormBase):
    """Filter options and columns to display for a registrations list of an event"""

    def _process_GET(self):
        visible_columns = session.get('reg_list_columns', {'items': [], 'user_info': []})
        return WPManageRegistration.render_template('management/reglist_filter.html', self.event, regform=self.regform,
                                                    event=self.event, RegistrationFormItemType=RegistrationFormItemType,
                                                    visible_cols_regform_items=visible_columns['items'],
                                                    visible_cols_user_info=visible_columns['user_info'],
                                                    user_info=USER_INFO)

    def _process_POST(self):
        visible_regform_items = json.loads(request.values['visible_cols_regform_items'])
        visible_user_info = json.loads(request.values['visible_cols_user_info'])
        if not session.get('reg_list_columns'):
            session['reg_list_columns'] = {}
        session['reg_list_columns']['items'] = visible_regform_items
        session['reg_list_columns']['user_info'] = visible_user_info
        session.modified = True
        regform_items = RegistrationFormItem.find_all(RegistrationFormItem.id.in_(visible_regform_items))
        tpl = get_template_module('events/registration/management/_reglist.html')
        reg_list = tpl.render_registrations_list(regform=self.regform, visible_cols_regform_items=regform_items,
                                                 visible_cols_user_info=visible_user_info, user_info=USER_INFO,
                                                 get_registration_field_data=get_registration_field_data,
                                                 get_user_info=get_user_info)
        return jsonify_data(registrations_list=reg_list)