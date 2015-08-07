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

import mimetypes
from io import BytesIO
from itertools import count

from flask import flash, redirect, request, jsonify
from werkzeug.exceptions import BadRequest, NotFound

from indico.core.db import db
from indico.core.db.sqlalchemy.util.models import get_default_values
from indico.modules.events.layout import layout_settings
from indico.modules.events.layout.forms import LayoutForm, MenuEntryForm, MenuLinkForm, MenuPageForm
from indico.modules.events.layout.models.menu import MenuEntry, MenuEntryType, MenuPage
from indico.modules.events.layout.util import menu_entries_for_event, move_entry, get_event_logo
from indico.modules.events.layout.views import WPLayoutEdit, WPMenuEdit
from indico.modules.events.models.events import Event
from indico.util.i18n import _
from indico.web.flask.templating import get_template_module
from indico.web.flask.util import redirect_or_jsonify, url_for, send_file
from indico.web.forms.base import FormDefaults
from indico.web.util import jsonify_data, jsonify_template
from MaKaC.webinterface.rh.conferenceModif import RHConferenceModifBase
from MaKaC.webinterface.rh.conferenceDisplay import RHConferenceBaseDisplay


def _render_menu_entry(entry):
    tpl = get_template_module('events/layout/_menu.html')
    return tpl.menu_entry(entry=entry)


def _render_menu_entries(event, show_hidden=False):
    tpl = get_template_module('events/layout/_menu.html')
    return tpl.menu_entries(menu_entries_for_event(event, show_hidden=show_hidden))


class RHLayoutLogoUpload(RHConferenceModifBase):
    CSRF_ENABLED = True

    def _process(self):
        event = Event.find(Event.id == self._conf.getId()).one()
        f = request.files.get('file')
        content = f.read()
        event.logo = content
        content_type = mimetypes.guess_type(f.filename)[0] or f.mimetype or 'application/octet-stream'
        event.logo_metadata = {
            'size': len(content),
            'file_name': f.filename,
            'content_type': content_type
        }
        return jsonify({'success': True})


class RHLogoDisplay(RHConferenceBaseDisplay):
    def _process(self):
        logo_data = get_event_logo(self._conf)
        logo_content = BytesIO(logo_data['content'])
        metadata = logo_data['metadata']
        return send_file(metadata['file_name'], logo_content, mimetype=metadata['content_type'], no_cache=True,
                         conditional=True)


class RHLayoutEdit(RHConferenceModifBase):
    def _process(self):
        defaults = FormDefaults(**layout_settings.get_all(self._conf))
        event = Event.find(Event.id == self._conf.getId()).one()
        form = LayoutForm(event=event, obj=defaults)
        if form.validate_on_submit():
            layout_settings.set_multi(self._conf, {
                'is_searchable': form.data['is_searchable'],
                'show_nav_bar': form.data['show_nav_bar'],
                'show_social_badges': form.data['show_social_badges'],
                'show_banner': form.data['show_banner'],
                'header_text_color': form.data['header_text_color'],
                'header_background_color': form.data['header_background_color'],
                'announcement': form.data['announcement'],
                'show_announcement': form.data['show_announcement']
            })
            flash(_('Settings saved'), 'success')
            return redirect(url_for('event_layout.index', self._conf))
        else:
            if event.logo:
                form.logo.data = {
                    'url': url_for('event_images.logo-display', self._conf),
                    'file_name': event.logo_metadata['file_name'],
                    'size': event.logo_metadata['size'],
                    'content_type': event.logo_metadata['content_type']
                }
        return WPLayoutEdit.render_template('layout.html', self._conf, form=form, event=self._conf)


class RHMenuEdit(RHConferenceModifBase):
    def _process(self):

        return WPMenuEdit.render_template('menu_edit.html', self._conf, event=self._conf, MenuEntryType=MenuEntryType,
                                          menu=menu_entries_for_event(self._conf, show_hidden=True))


class RHMenuEntryEditBase(RHConferenceModifBase):
    def _checkParams(self, params):
        RHConferenceModifBase._checkParams(self, params)
        self.entry = MenuEntry.find_first(id=request.view_args['menu_entry_id'], event_id=self._conf.getId())
        if not self.entry:
            raise NotFound


class RHMenuEntryEdit(RHMenuEntryEditBase):
    def _process(self):
        defaults = FormDefaults(self.entry)
        form_cls = MenuEntryForm
        if self.entry.is_user_link:
            form_cls = MenuLinkForm
        elif self.entry.is_page:
            form_cls = MenuPageForm
            defaults['html'] = self.entry.page.html
        form = form_cls(linked_object=self.entry, obj=defaults)
        if form.validate_on_submit():
            form.populate_obj(self.entry)
            return jsonify_data(entry=_render_menu_entry(self.entry))
        return jsonify_template('events/layout/menu_entry_form.html', form=form)


class RHMenuEntryPosition(RHMenuEntryEditBase):
    def _process(self):
        position = request.form.get('position')
        try:
            position = int(position)
        except ValueError:
            if position:
                return jsonify_data(success=False)
            position = None
        move_entry(self.entry, position)
        return jsonify_data()


class RHMenuEnableEntry(RHMenuEntryEditBase):
    def _process(self):
        self.entry.is_enabled = not self.entry.is_enabled
        return redirect_or_jsonify(url_for('.menu', self._conf), is_enabled=self.entry.is_enabled)


class RHMenuAddEntry(RHConferenceModifBase):
    def _process(self):
        defaults = FormDefaults(get_default_values(MenuEntry))
        form_cls = None
        entry_type = request.args['type']

        if entry_type == MenuEntryType.separator.name:
            entry = MenuEntry(event_id=self._conf.id, type=MenuEntryType.separator)
            db.session.add(entry)
            db.session.flush()
            return jsonify_data(entry=_render_menu_entry(entry))

        elif entry_type == MenuEntryType.user_link.name:
            form_cls = MenuLinkForm
        elif entry_type == MenuEntryType.page.name:
            form_cls = MenuPageForm
        else:
            raise BadRequest

        form = form_cls(obj=defaults)
        if form.validate_on_submit():
            entry = MenuEntry(
                event_id=self._conf.id,
                type=MenuEntryType[entry_type]
            )
            form.populate_obj(entry, skip={'html'})

            if entry.is_page:
                entry.page = MenuPage(html=form.html.data)

            db.session.add(entry)
            db.session.flush()
            return jsonify_data(entry=_render_menu_entry(entry))
        return jsonify_template('events/layout/menu_entry_form.html', form=form)


class RHMenuDeleteEntry(RHMenuEntryEditBase):
    def _process(self):
        if self.entry.type not in (MenuEntryType.user_link, MenuEntryType.page, MenuEntryType.separator):
            raise BadRequest('Menu entry of type {} cannot be deleted'.format(self.entry.type.name))

        position_gen = count(self.entry.position)
        if self.entry.children:
            for child in self.entry.children:
                child.parent_id = self.entry.parent_id
                child.position = next(position_gen)

        with db.session.no_autoflush:
            entries = MenuEntry.find_all(MenuEntry.event_id == self.entry.event_id,
                                         MenuEntry.parent_id == self.entry.parent_id,
                                         MenuEntry.position >= self.entry.position,
                                         MenuEntry.id != self.entry.id)
        for entry in entries:
            entry.position = next(position_gen)

        db.session.delete(self.entry)
        db.session.flush()

        return jsonify_data(menu=_render_menu_entries(self._conf, show_hidden=True))