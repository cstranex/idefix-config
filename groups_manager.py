import os
from urllib.parse import urlparse, urljoin

from gi.repository import Gtk, Gdk

from myconfigparser import myConfigParser
from repository import fetch_repository_list
from util import showwarning, askyesno, ask_text, ip_address_test

IMPORT_COLUMN_SELECTED = 0
IMPORT_COLUMN_NAME = 1
IMPORT_COLUMN_PATH = 2


class GroupManager:
    groups_store = None
    groups_changed = False
    buffer = None
    widgets = {}
    imported_groups = False

    # If we encounter a group that already exists
    # if None - ask the user what to do
    # True - Merge
    # False - Replace
    merge_in_group = None

    def __init__(self, arw, controller):
        self.arw = arw
        self.controller = controller

    def show(self):
        widgets = Gtk.Builder()
        widgets.add_from_file('./groups_manager.glade')
        widgets.connect_signals(self)
        self.widgets = {}
        for z in widgets.get_objects():
            try:
                name = Gtk.Buildable.get_name(z)
                self.widgets[name] = z
                z.name = name
            except:
                pass
        self.widgets['groups_window'].show()
        self.groups_store = self.widgets['groups_store']
        self.action_edit_groups(None)
        self.groups_changed = False
        self.buffer = None
        self.imported_groups = False

    def hide(self, *args):
        self.groups_changed = False
        self.imported_groups = False
        self.widgets['groups_window'].hide()

    def save(self, *args):
        if self.imported_groups:
            dialog = Gtk.Dialog()
            dialog.set_transient_for(self.widgets['groups_window'])
            dialog.add_button(_("Merge"), Gtk.ResponseType.APPLY)
            dialog.add_button(_("Replace"), Gtk.ResponseType.ACCEPT)
            dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
            label = Gtk.Label(_("Do you want to merge groups or replace existing?"))
            dialog.get_content_area().add(label)
            dialog.show_all()
            result = dialog.run()
            dialog.hide()
            if result == Gtk.ResponseType.APPLY:
                # Merge case
                if not self.merge():
                    return
            elif result == Gtk.ResponseType.ACCEPT:
                # Replace
                self.save_groups()
        else:
            self.save_groups()

        self.hide()

    def ask_merge(self, name):
        dialog = Gtk.Dialog()
        dialog.set_transient_for(self.widgets['groups_window'])
        dialog.add_button(_("Replace"), Gtk.ResponseType.APPLY)
        dialog.add_button(_("Replace all"), Gtk.ResponseType.ACCEPT)
        dialog.add_button(_("Merge"), Gtk.ResponseType.OK)
        dialog.add_button(_("Merge all"), Gtk.ResponseType.YES)
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dialog.get_content_area().add(Gtk.Label(_("Duplicate group %s found") % name))
        dialog.show_all()
        result = dialog.run()
        dialog.hide()
        if result == Gtk.ResponseType.APPLY:
            return False
        elif result == Gtk.ResponseType.ACCEPT:
            self.merge_in_group = False
            return False
        elif result == Gtk.ResponseType.OK:
            return True
        elif result == Gtk.ResponseType.YES:
            self.merge_in_group = True
            return True
        else:
            return None

    @staticmethod
    def merge_group(new, original):
        """Merge contents of new and original"""
        values = set()
        values.update(new)
        values.update(original)
        return list(values)

    def merge(self):
        """Go through each item in our store vs the controller store and look for differences"""
        groups = {}

        original_groups = {}
        for row in self.controller.groups_store:
            original_groups[row[0]] = row[1].split('\n')

        new_groups = {}
        for row in self.groups_store:
            new_groups[row[0]] = row[1].split('\n')

        for key in new_groups:
            if key not in original_groups:
                groups[key] = new_groups[key]
            else:
                # What is our merge strategy?
                if self.merge_in_group is None:
                    # Ask the user what to do
                    merge = self.ask_merge(key)
                    if merge is None:
                        return
                else:
                    merge = self.merge_in_group

                if merge is True:
                    # Merge within the group
                    groups[key] = self.merge_group(new_groups[key], original_groups[key])
                elif merge is False:
                    # Replace
                    groups[key] = new_groups[key]

                original_groups.pop(key)

        # Now go through the original group
        for key in original_groups:
            groups[key] = original_groups[key]

        # And finally write
        self.controller.groups_store.clear()
        for key, value in groups.items():
            self.controller.groups_store.append((key, '\n'.join(value)))

        return True

    def save_groups(self, *args):
        """Update the group"""
        self.controller.groups_store.clear()
        for row in self.groups_store:
            self.controller.groups_store.append((row[0], row[1]))

    def selection_changed(self, widget):
        if self.groups_changed:
            showwarning(_("Save"), _("Don't forget to save"), 2)
            self.groups_changed = False

        model, iter = widget.get_selected()

        self.buffer = Gtk.TextBuffer()
        self.buffer.set_text(model.get_value(iter, 1))
        self.buffer.connect('changed', self.set_groups_dirty)
        self.widgets['groups_view'].set_buffer(self.buffer)

    def set_groups_dirty(self, widget):
        """Mark that the group entry was edited and update it"""
        self.groups_changed = True
        model, iter = self.widgets['groups_tree'].get_selection().get_selected()
        model.set_value(iter, 1, self.buffer.get_text(
            self.buffer.get_start_iter(),
            self.buffer.get_end_iter(),
            False
        ))

    def action_edit_groups(self, widget):
        """Show the groups in the tree view to allow the user to edit """
        if self.imported_groups or self.groups_changed:
            if askyesno(_("Save Changes"), _("Do you want to save your changes?")):
                self.save_groups()

        self.imported_groups = False
        self.groups_changed = False

        self.groups_store.clear()
        for row in self.controller.groups_store:
            self.groups_store.append((row[0], row[1]))

    def action_import_groups(self, widget):
        """Imports groups from an ini file, first adds them into the tree view for later merging/replacing"""
        if self.groups_changed:
            if askyesno(_("Save Changes"), _("Do you want to save your changes?")):
                self.save_groups()

        self.groups_changed = False

        dialog = Gtk.FileChooserDialog(
            _("Import File"),
            self.widgets['groups_window'],
            Gtk.FileChooserAction.OPEN,
            (_("Import"), Gtk.ResponseType.ACCEPT),
        )
        file_filter = Gtk.FileFilter()
        file_filter.add_pattern('*.ini')
        dialog.set_filter(file_filter)

        self.groups_store.clear()
        dialog.show_all()
        response = dialog.run()
        if response == Gtk.ResponseType.ACCEPT:

            parser = myConfigParser()
            data1 = parser.read(dialog.get_filename(), "groups", comments=True)['groups']
            for key in data1:
                tooltip = "\n".join(data1[key].get('dest_domain', ''))
                if data1[key].get('dest_ip', ''):
                    if tooltip:
                        tooltip += '\n'
                    tooltip += "\n".join(data1[key].get('dest_ip', ''))
                self.groups_store.append([key, tooltip])

            self.imported_groups = True

        dialog.destroy()

    def action_export_groups(self, widget):
        """Export the groups in the main group store into an ini file"""

        dialog = Gtk.FileChooserDialog(
            _("Export File"),
            self.widgets['groups_window'],
            Gtk.FileChooserAction.SAVE,
            (_("Export"), Gtk.ResponseType.ACCEPT),
        )
        file_filter = Gtk.FileFilter()
        file_filter.add_pattern('*.ini')
        dialog.set_filter(file_filter)

        dialog.show_all()
        response = dialog.run()
        if response == Gtk.ResponseType.ACCEPT:

            data = ''

            for row in self.controller.groups_store:
                data += '\n[%s]\n' % row[0]
                for domain in row[1].split('\n'):
                    if ip_address_test(domain):
                        data += 'dest_ip = %s\n' % domain
                    else:
                        data += 'dest_domain = %s\n' % domain

            with open(dialog.get_filename(), 'w', encoding="utf-8-sig", newline="\n") as f:
                f.write(data)

        dialog.destroy()

    def action_import_repository(self, widget):
        if self.imported_groups or self.groups_changed:
            if askyesno(_("Save Changes"), _("Do you want to save your changes?")):
                self.save_groups()

        self.imported_groups = False
        self.groups_changed = False

        # Get repository file from server
        data = fetch_repository_list()
        if not data:
            showwarning(_("Repository"), _("Could not get files from server"))
            return

        self.widgets['repository_store'].clear()

        path_iters = {
            '/': None
        }

        for path, files in data:
            directory = urlparse(path).path
            if directory.endswith('/'):
                directory = directory[:-1]

            parent_path, name = os.path.split(directory)
            if not name:
                name = 'all'

            if parent_path not in path_iters:
                path_iters[parent_path] = self.widgets['repository_store'].append(None)
                self.widgets['repository_store'].set_value(
                    path_iters[parent_path],
                    IMPORT_COLUMN_NAME, os.path.split(parent_path)[1])
                self.widgets['repository_store'].set_value(
                    path_iters[parent_path],
                    IMPORT_COLUMN_PATH, path)

            parent = self.widgets['repository_store'].append(path_iters[parent_path])
            path_iters[directory] = parent

            self.widgets['repository_store'].set_value(parent, IMPORT_COLUMN_NAME, name)
            self.widgets['repository_store'].set_value(parent, IMPORT_COLUMN_PATH, path)
            for file in files:
                if file.endswith('.json'):
                    # Only import ini files for now
                    continue

                iter = self.widgets['repository_store'].append(parent)

                full_path = urljoin(path, file)

                self.widgets['repository_store'].set_value(iter, IMPORT_COLUMN_NAME, file)
                self.widgets['repository_store'].set_value(iter, IMPORT_COLUMN_PATH, full_path)

        self.widgets['import_window'].show_all()

    def action_cancel_repository(self, widget):
        self.widgets['import_window'].hide()

    def action_start_repository_import(self, widget):
        """Process the user selection and import the proxy groups"""
        pass

    def show_context(self, widget, event):
        if event.type != Gdk.EventType.BUTTON_RELEASE or event.button != 3:
            return
        self.widgets["context_menu"].popup(None, None, None, None, event.button, event.time)

    def rename_item(self, widget):
        """Rename an entry"""
        model, iter = self.widgets['groups_tree'].get_selection().get_selected()
        name = model.get_value(iter, 0)
        value = ask_text(self.widgets['groups_window'], _("Rename Group"), name)
        model.set_value(iter, 0, value)
        self.groups_changed = True

    def delete_item(self, widget):
        """Delete an entry"""
        model, iter = self.widgets['groups_tree'].get_selection().get_selected()
        name = model.get_value(iter, 0)
        if askyesno(_("Delete Group"), _("Do you want to delete %s?" % name)):
            model.remove(iter)
            self.groups_changed = True

    def update_import_selection(self, widget, path):
        iter = self.widgets['repository_store'].get_iter(path)
        self.widgets['repository_store'].set_value(iter, IMPORT_COLUMN_SELECTED, not widget.get_active())
