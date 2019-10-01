import json
import shutil
from collections import OrderedDict

from gi.repository import Gtk

from util import get_config_path


class ImportJsonDialog:

    def __init__(self, arw, controller, merge = False):
        self.arw = arw
        self.controller = controller
        self.merge = merge

        self.file_filter = Gtk.FileFilter()
        self.file_filter.add_pattern('*.json')

    def run(self):
        dialog = Gtk.FileChooserDialog(
            _("Import Config"),
            self.arw['window1'],
            Gtk.FileChooserAction.OPEN,
            (_("Import"), Gtk.ResponseType.ACCEPT),
        )
        dialog.set_filter(self.file_filter)

        response = dialog.run()
        if response == Gtk.ResponseType.ACCEPT:
            config = json.load(
                open(dialog.get_filename(), 'r'),
                object_pairs_hook=OrderedDict
            )

            if self.merge :
                # merge the opened config with the existing one

                if 'users' in config:
                    for user in config['users']:
                        if user not in self.controller.config['users']:
                            self.controller.config['users'][user] = OrderedDict()
                        self.controller.config['users'][user].update(config['users'][user])

                if 'proxy' in config:
                    for proxy in config['proxy']:
                        if proxy not in self.controller.config['proxy']:
                            self.controller.config['proxy'][proxy] = OrderedDict()
                        self.controller.config['proxy'][proxy].update(config['proxy'][proxy])

                if 'ports' in config:
                    for port in config['ports']:
                        if port not in self.controller.config['ports']:
                            self.controller.config['ports'][port] = OrderedDict()
                        self.controller.config['ports'][port].update(config['ports'][port])

                if 'groups' in config:
                    for group in config['groups']:
                        if group not in self.controller.config['groups']:
                            self.controller.config['groups'][group] = OrderedDict()
                        self.controller.config['groups'][group].update(config['groups'][group])

                if 'firewall' in config:
                    for firewall in config['firewall']:
                        if firewall not in self.controller.config['firewall']:
                            self.controller.config['firewall'][firewall] = OrderedDict()
                        self.controller.config['firewall'][firewall].update(config['firewall'][firewall])
            else :
                self.controller.config = config
                self.controller.update()
            self.update_gui()
        dialog.destroy()

    def update_gui(self):
        self.controller.maclist = self.controller.users.create_maclist()
        self.controller.users.populate_users()
        self.controller.proxy_users.populate_proxy()
        #self.controller.populate_ports()
        self.controller.populate_groups()
        self.controller.populate_users_chooser()
        #self.controller.firewall.populate_firewall()
        self.controller.set_check_boxes()
        self.controller.set_colors()




class ExportJsonDialog:
    def __init__(self, arw, controller):
        self.arw = arw
        self.controller = controller

        self.file_filter = Gtk.FileFilter()
        self.file_filter.add_pattern('*.json')

    def run(self):
        dialog = Gtk.FileChooserDialog(
            _("Export Config"),
            self.arw['window1'],
            Gtk.FileChooserAction.SAVE,
            (_("Export"), Gtk.ResponseType.ACCEPT),
        )
        dialog.set_filter(self.file_filter)

        response = dialog.run()
        if response == Gtk.ResponseType.ACCEPT:
            shutil.copy(get_config_path("idefix.json"), dialog.get_filename())

        dialog.destroy()
