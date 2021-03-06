from configparser import ConfigParser

import time
from gi.repository import Gdk, Gtk

from actions import DRAG_ACTION
from util import askyesno, ask_text, name_sorter


class ProxyGroup:
    mem_time = 0
    editing_iter = None

    def __init__(self, arw, controller):
        self.arw = arw
        self.controller = controller
        self._active_store = 'proxy'

        self.arw["proxy_group"].enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, [], DRAG_ACTION)
        self.arw['proxy_group'].drag_source_add_text_targets()
        self.arw['proxy_group'].connect("drag-data-get", self.proxy_group_data_get)
        self.arw['proxy_group'].drag_dest_set(Gtk.DestDefaults.DROP, [], DRAG_ACTION)
        self.arw['proxy_group'].drag_dest_add_text_targets()
        self.arw['proxy_group'].connect("drag-data-received", self.update_proxy_group_list_view)
        self.arw['proxy_group'].get_model().set_default_sort_func(name_sorter)
        self.proxy_group_domain_store = self.arw['proxy_group_domain_store']

        # The store for the proxy_groups in a particular proxy
        self.proxy_group_store = self.arw['proxy_groups_store']

        # The store for each proxy group
        self.groups_store = Gtk.ListStore(str, str)
        self.ports_store = self.arw['ports_list']
        self.chooser_sort = Gtk.TreeModelSort.sort_new_with_model(self.groups_store)

        self.proxy_group_window = self.arw['proxy_group_window']

        for scroll in ['proxy_group', 'chooser']:
            ctx = self.arw[scroll].get_style_context()
            ctx.add_class('chosen_list')

    @property
    def current_store(self):
        """Returns the currently selected store"""
        if self._active_store == 'proxy':
            return self.groups_store
        elif self._active_store == 'port':
            return self.ports_store

    def set_group_store(self, name='proxy'):
        if name == 'proxy':
            self.chooser_sort = Gtk.TreeModelSort.sort_new_with_model(self.groups_store)
            self._active_store = 'proxy'
        elif name == 'port':
            self.chooser_sort = Gtk.TreeModelSort.sort_new_with_model(self.ports_store)
            self._active_store = 'port'

        self.chooser_sort.set_sort_column_id(0, Gtk.SortType.ASCENDING)
        self.arw["chooser"].set_model(self.chooser_sort)

    def proxy_group_data_get(self, treeview, drag_context, data, info, time):

        (model, iter1) = treeview.get_selection().get_selected()

        iter1 = model.convert_iter_to_child_iter(iter1)
        model = model.get_model(model)

        if iter1:
            path = model.get_string_from_iter(iter1)
            data.set_text(path, -1)
            print("DRAG", path)

    def proxy_group_select(self, widget, event):
        if event.type == Gdk.EventType.BUTTON_RELEASE:
            if event.button == 3:  # right click, runs the context menu
                self.arw["proxy_groups_menu"].popup(None, None, None, None, event.button, event.time)

    def update_proxy_group_list(self, proxy_iter=None):
        if not proxy_iter:
            proxy_iter = self.controller.iter_filter

        if not proxy_iter:
            return None

        domains = {}
        for row in self.current_store:
            domains[row[0]] = row[1]

        self.proxy_group_store.clear()
        group_iter = self.controller.filter_rules.current_store[proxy_iter]
        if not group_iter:
            return None
        groups = group_iter[7]
        if not groups:
            return None
        for name in groups.split('\n'):
            if name:
                iter = self.proxy_group_store.append()
                self.proxy_group_store.set_value(iter, 0, name)

                if name in domains:
                    tooltip = domains[name]
                else:
                    tooltip = _("(error)")

                self.proxy_group_store.set_value(iter, 1, tooltip)

    def show_import_proxy_group_window(self, widget):
        """Opens a dialog to import the proxy group"""

        # Clear the import buffer
        buf = self.arw['proxy_group_import_view'].get_buffer()
        buf.set_text('')

        self.arw['import_proxy_group_dialog'].show_all()
        if not self.arw['import_proxy_group_dialog'].run():
            self.arw['import_proxy_group_dialog'].hide()
            return

        # Start Importing
        parser = ConfigParser()
        # TODO: This needs modification
        data = parser.read(
            buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).split('\n'),
            'groups',
            isdata=True
        )
        if not data:
            print("Error parsing data")

        for key in data['groups']:
            tooltip = '\n'.join(data['groups'][key].get('dest_domain', ''))
            if data['groups'][key].get('dest_ip', ''):
                if tooltip:
                    tooltip += '\n'
                tooltip += '\n'.join(data['groups'][key].get('dest_ip', ''))

            if 'lines' in data['groups'][key]:
                if tooltip:
                    tooltip += '\n'
                tooltip += data['groups'][key]['lines']

            new_iter = self.current_store.append()
            self.current_store.set_value(new_iter, 0, key)
            self.current_store.set_value(new_iter, 1, tooltip)

        self.arw['import_proxy_group_dialog'].hide()

    def delete_proxy_group(self, widget):
        model, iter = self.arw['proxy_group'].get_selection().get_selected()
        name = model.get_value(iter, 0).strip()

        names = self.controller.filter_rules.current_store.get_value(self.controller.iter_filter, 7).split('\n')
        if name not in names or name == 'any':
            return

        res = askyesno("Remove group", "Do you want to remove group %s?" % name)
        if not res:
            return

        names.remove(name)

        self.controller.filter_rules.current_store.set_value(self.controller.iter_filter, 7, '\n'.join(names))
        self.update_proxy_group_list()

    def update_proxy_group_list_view(self, widget, ctx, x, y, data, info, etime):
        """Add a proxy group to the list"""
        position = None
        if not self.controller.iter_filter:
            return

        if time.time() - self.mem_time < 1:  # dirty workaround to prevent two drags
            return
        self.mem_time = time.time()

        model = widget.get_model()
        data1 = data.get_text().split("#")
        if not data1[1] == "chooser":      # if data does not come from the right chooser, return
            return
        path = data1[0]
        if len(data1) == 2 :
            source_model = self.arw[data1[1]].get_model()
        else:
            source_model = model

        try:
            iter_source = source_model.get_iter(path)
            values = [source_model.get_value(iter_source, i) for i in range(model.get_n_columns())]
        except TypeError:
            iter_source = None
            values = None

        """
        dest = widget.get_dest_row_at_pos(x, y)
        if dest:
            drop_path, position = dest
            iter1 = model.get_iter(drop_path)

            if (position == Gtk.TreeViewDropPosition.BEFORE
                    or position == Gtk.TreeViewDropPosition.INTO_OR_BEFORE):
                iter_dest = model.insert_before(iter1, ['' for x in range(model.get_n_columns())])
            else:
                iter_dest = model.insert_after(iter1, ['' for x in range(model.get_n_columns())])
        else:
        """
        model = model.get_model()
        iter_dest = model.insert(-1)

        if iter_source:
            for i in range(model.get_n_columns()):
                model.set_value(iter_dest, i, values[i])
            if source_model == model:     # move row in the list
                model.remove(iter_source)
            names = [name[0] for name in model]
            if names is None:
                names = ['']
            self.controller.filter_rules.current_store.set_value(self.controller.iter_filter, 7, '\n'.join(names))
            return

        new_name = data.get_text().strip()

        names = self.controller.filter_rules.current_store.get_value(self.controller.iter_filter, 7).split('\n')
        if new_name in names:
            return
        names.append(new_name)
        self.controller.filter_rules.current_store.set_value(self.controller.iter_filter, 7, '\n'.join(names))
        self.update_proxy_group_list(self.controller.iter_filter)

    def edit_proxy_group(self, widget):
        """Edit proxy group selected in proxy_group or chooser tree"""
        model, iter = widget.get_selection().get_selected()
        if not iter:
            return

        name = model.get_value(iter, 0)

        # Find the name in the proxy_group_store
        for proxy_row in self.current_store:
            if proxy_row[0] == name:
                self.edit_group(proxy_row.iter)

    def edit_group(self, iter):
        """If the filter is proxy or dns then edit using the proxy_window. if ports then use the ports_window"""
        self.editing_iter = iter

        if self._active_store == 'port':
            # Find the correct port group to show in the ports window
            self.controller.firewall.ports_open_window()
            valid, tree_iter = self.arw['ports_tree'].get_model().convert_child_iter_to_iter(iter)
            if valid:
                self.arw['ports_tree'].get_selection().select_iter(tree_iter)
        else:
            self.proxy_group_domain_store.clear()
            for domain in self.current_store.get_value(iter, 1).split('\n'):
                if not domain or domain.startswith('('):
                    continue
                new_iter = self.proxy_group_domain_store.append()
                self.proxy_group_domain_store.set_value(new_iter, 0, domain)
            self.proxy_group_window.show_all()
            self.arw['proxy_group_message_label'].set_label(_("Editing %s") % self.current_store.get_value(iter, 0))

    def new_proxy_group(self, widget):
        """Create a new filter group and open it for editing"""
        name = ask_text(self.arw['window1'], _("New group name"))
        if not name:
            return
        new_iter = self.current_store.append()
        self.current_store.set_value(new_iter, 0, name)
        self.current_store.set_value(new_iter, 1, '')
        self.edit_group(new_iter)

    def proxy_group_add_item(self, widget):
        """Add a new domain to the list"""
        text = ask_text(self.proxy_group_window, _("Enter a domain name"))
        if not text:
            return
        iter = self.proxy_group_domain_store.append()
        self.proxy_group_domain_store.set_value(iter, 0, text)

    def proxy_group_remove_item(self, widget):
        """When right clicked, Remove the selected item from the list"""
        model, iter = self.arw['proxy_group_domain_tree'].get_selection().get_selected()
        if not iter:
            return
        domain = model.get_value(iter, 0)
        if askyesno(_("Remove domain?"), _("Remove domain: %s") % domain):
            model.remove(iter)

    def proxy_group_edit_item(self, widget):
        """When right clicked, Edit the selected item from the list"""
        model, iter = self.arw['proxy_group_domain_tree'].get_selection().get_selected()
        domain = model.get_value(iter, 0)
        domain = ask_text(self.proxy_group_window, _("Edit domain name"), domain)
        model.set_value(iter, 0, domain)

    def proxy_group_finished(self, widget):
        """Finish editing the proxy group"""
        self.proxy_group_window.hide()
        self.current_store.set_value(
            self.editing_iter, 1, '\n'.join(row[0] for row in self.proxy_group_domain_store)
        )
        if not len(self.current_store.get_value(self.editing_iter, 0).split('\n')):
            self.current_store.set_value(self.editing_iter, 0, _("(error)"))
        self.proxy_group_domain_store.clear()
        self.update_proxy_group_list()

    def proxy_group_domain_show_context(self, widget, event):
        """Show the context menu on right click"""
        if event.type == Gdk.EventType.BUTTON_RELEASE:
            if event.button == 3:  # right click, runs the context menu
                self.arw["proxy_group_domain_edit_menu"].popup(None, None, None, None, event.button, event.time)
