import http.client
import http.client
import io
import ipaddress
import json
import os
import subprocess
import time
from collections import OrderedDict

from gi.repository import Gtk

from ftp_client import ftp_connect, ftp_get
from util import showwarning, get_ip_address

# version 2.3.19 - Edit files added

WHY_COLUMN_NAME = 0
WHY_COLUMN_DOMAIN = 1
WHY_COLUMN_INFO = 2
WHY_COLUMN_RULE_TYPE = 3
WHY_COLUMN_RULE_DISABLED = 4
WHY_COLUMN_RULE_INVALID = 5


def me(string) :   # Markup Escape
    return string.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

class ExportDiagnosticDialog:
    def __init__(self, arw, controller):
        self.arw = arw
        self.controller = controller

        #self.file_filter = Gtk.FileFilter()
        #self.file_filter.add_pattern('*.json')

    def run(self, data1, configpath = None ):
        if not configpath:
            dialog = Gtk.FileChooserDialog(
                _("Export Config"),
                self.arw['window1'],
                Gtk.FileChooserAction.SAVE,
                (_("Export"), Gtk.ResponseType.ACCEPT),
            )
            #dialog.set_filter(self.file_filter)

            response = dialog.run()
            if response == Gtk.ResponseType.ACCEPT:
                configpath =    dialog.get_filename()
            dialog.destroy()

        f1 = open(configpath, "wb")
        f1.write(data1)
        f1.close()

class Information:
    def __init__(self, arw, controller):
        self.arw = arw
        self.controller = controller

    # the two following functions come from unbound-filter.py, and are slightly modified to add informations in the return
    def is_time_allowed(self, time_condition):
        local = time.localtime()
        hour = int(str(local[3]).rjust(2,"0") + str(local[4]).rjust(2,"0"))
        if time_condition["from"] < time_condition["to"]:                       # time window inside the same day
            if (hour > time_condition["from"]) and (hour < time_condition["to"]):
                return True
            else:
                return False
        else:                                                                   # time window overlaps midnight
            if (hour > time_condition["from"]) or (hour < time_condition["to"]):
                return True
            else:
                return False

    def is_allowed(self, user, domain, config):

        infos = {}
        infos["user"] = user
        infos["domain"] = domain
        infos["rules"] = OrderedDict()
        data1 = domain.split(".")
        data1.reverse()
        #data1 = data1[1:]       # the last element must be omitted

        for rule in config["rules"]:
            rule1 = config["rules"][rule]

            infos["rules"][rule] = {
                'enabled': rule1.get('active', 'on') == 'on',
            }

            # invalid rule
            if not (rule1.get("users") or rule1.get("any_user")):        # no user defined
                infos["rules"][rule].update({
                    'valid': False,
                    'reason': _('No user defined in this rule'),
                })
                continue
            if not "domains_tree" in rule1:                              # no destination defined
                infos['rules'][rule].update({
                    'valid': False,
                    'reason': _('No domain defined in this rule')
                })
                continue

            # user
            if not (rule1.get("any_user")  or  (user in rule1.get("users"))):       # user not allowed
                infos['rules'][rule].update({
                    'valid': True,
                    'user': False,
                    'reason': _('User is not allowed')
                })
                continue

            # time condition
            tc = rule1.get("time_condition")
            if tc:
                if not self.is_time_allowed(tc):
                    infos['rules'][rule].update({
                        'match': False,
                        'time_condition': False,
                        'reason': _('Time condition not satisfied'),
                    })
                    continue
                else:
                    infos['rules'][rule]['time_condition'] = True

            # action
            action = rule1.get("action") == "allow"

            # domain
            infos["rules"][rule]["domain"] = []
            base = rule1["domains_tree"]
            for i in range(len(data1)):
                if "*" in base:
                    infos["rules"][rule]["domain"].append("*")
                    infos["rules"][rule]["action"] = action
                    infos["rules"][rule]["rule"] = rule
                    return infos
                if not data1[i] in base:
                    break

                if i == len(data1) - 1:         # if this is the last element to check, we must verify if the next level is *
                                                # or nothing. If there were other elements to check, the permission must not be given.
                    if "*" in base[data1[i]]:
                        infos["rules"][rule]["domain"].append("*")
                        infos["rules"][rule]["action"] = action
                        infos["rules"][rule]["rule"] = rule
                        return infos
                    if len(base[data1[i]]) == 0:
                        infos["rules"][rule]["domain"].append("???")
                        infos["rules"][rule]["action"] = action
                        infos["rules"][rule]["rule"] = rule
                        return infos
                base = base[data1[i]]
                infos["rules"][rule]["domain"].append(data1[i])
        if not "no-match" in infos:
            infos["no-match"] = "No-match is empty, this is an error"
        return infos


    def find_idefix(self, widget = None):

        results = []
        checked = []
        if os.name == "nt":
            arp = subprocess.check_output(["arp", "-a"])
            arp = arp.decode("cp850")
            for line1 in arp.split("\n"):
                result = get_ip_address(line1)
                if result:
                    ip = result.group(0)
                    if ip in checked:       # no use to check a second time
                        continue
                    else:
                        checked.append(ip)
                    self.controller.arw["network_summary_status"].set_text(_("Connecting : " + ip))
                    while Gtk.events_pending():
                        Gtk.main_iteration()
                    h1 = http.client.HTTPConnection(ip)
                    try:
                        h1.connect()
                    except:
                        h1.close()
                        continue
                    h1.request("GET","/network-info.php")
                    res = h1.getresponse()
                    if res.status == 200:
                        content = res.read().decode("cp850")
                        # some devices which are protected by a password will give a positive (200) answer to any file name.
                        # We must check for a string which is specific to Idefix
                        if "idefix network info" in content:
                            h1.close()
                            results.append([ip, content])
                    h1.close()
            return results

    def getmac(self, widget):

        self.idefix_ip = ""
        # clear data
        for widget in ["network_summary_label1", "network_summary_label2", "network_summary_label3"]:
            self.arw[widget].set_text("")
        self.arw["network_summary"].show()
        message = ""
        self.arw["network_summary_spinner"].start()
        if os.name == "nt":
            getmac_txt = subprocess.check_output(["getmac", "-v"]).decode("cp850")
            x = getmac_txt.replace("\r", "").split("\n")

            for line in x:
                x = line.strip()
                if x[0:3] == "===":
                    x = x[0:60]
                x = x.replace(" ", "  ")
                #x = re.sub("(\s)", "§", x)
                message += x + "\n"
            self.arw["network_summary_label1"].set_text(message)
            while Gtk.events_pending():
                        Gtk.main_iteration()
        else:
            pass  # TODO : code for Linux and Mac

        # find Idefix and display network settings
        found = self.find_idefix()

        if not found:
            message += "<b>Idefix not found ! </b>"
            self.arw["network_summary_label2"].set_markup(message)
        else:
            message = ""
            for (ip, content) in found:

                self.idefix_ip = ip
                if content:

                    message += '<b><span foreground="green">Idefix found at ' + ip + "</span></b>"
                    network = json.loads(content)
                    # check validity to avoid errors
                    for key in ["eth1", "netmask1", "link_eth1", "eth0", "netmask0", "link_eth0", "gateway"]:
                        if not key in network["idefix"]:
                            network["idefix"][key] = ""
                    message += _("\n\n     Local port (eth1) IP : ") + network["idefix"].get("eth1")
                    message += _("\n     Local port (eth1) Netmask : ") + network["idefix"]["netmask1"]
                    if "yes" in network["idefix"]["link_eth1"]:
                        message += _('\n<span foreground="green">     Idefix port (eth1) active : yes </span>')
                    else:
                        message += _('\n<span foreground="red">     Idefix port (eth1) active : no </span>')

                    message += _("\n\n     Internet port (eth0) IP : ") + network["idefix"].get("eth0")
                    message += _("\n     Internet port (eth0) Netmask : ") + network["idefix"]["netmask0"]
                    if "yes" in network["idefix"]["link_eth0"]:
                        message += _('\n<span foreground="green">     Idefix port (eth0) active : yes </span>')
                    else:
                        message += _('\n<span foreground="red">     Idefix port (eth0) active : no </span>')
                    message += _("\n\n              Gateway : ") + network["idefix"]["gateway"]
                    message += "\n\n"

                    if network["idefix"]["eth0"] != "" and network["idefix"]["eth1"] != "":
                        wan = ipaddress.ip_interface(network["idefix"]["eth0"] + "/" + network["idefix"]["netmask0"])
                        lan = ipaddress.ip_interface(network["idefix"]["eth1"] + "/" + network["idefix"]["netmask1"])

                        if lan.network.overlaps(wan.network):
                            message += "\n\n<b>WARNING !!!  WARNING !!!  WARNING !!!  WARNING !!! \n Both subnets overlap !\nIdefix cannot work</b>"

                    supervix = "http://" + ip + ":10080/visu-donnees-systeme.php"
                    self.arw["network_summary_label2"].set_markup(message)
                    while Gtk.events_pending():
                                Gtk.main_iteration()

            # verify Idefix Internet connection
            self.controller.arw["network_summary_status"].set_text(_("Ping gateway from Idefix "))
            while Gtk.events_pending():
                Gtk.main_iteration()
            ping_data = json.loads(self.get_infos("ping"))
            self.arw["network_summary_spinner"].stop()
            if ping_data:
                message = "\n<b>Internet connexion : for %s </b>\n" % self.controller.ftp_config["server"]
                for test in ping_data:
                    message1 = "ping %s (%s) : " % (test, ping_data[test]["id"])
                    if ping_data[test]["ping"] == 0:
                        message += '<span foreground="green">' + message1 + _("OK") + "</span>\n"
                    else:
                        message += '<span foreground="red">' + message1 + _("failed") + "</span>\n"
            else:
                message += "Open a connection for this Idefix, and resend the command.\n"
                message += "It will then be able to test if Idefix Internet connection is working."
            self.arw["network_summary_label3"].set_markup(message)

            self.controller.arw["network_summary_status"].set_text(_("Ping Idefix eth1 "))
            while Gtk.events_pending():
                Gtk.main_iteration()


            network = json.loads(found[0][1])
            test_ip = network["idefix"]["eth1"]
            result = subprocess.check_output(["ping", "-n", "1", test_ip ]).decode("cp850")
            if "TTL" in result:
                message += "%s Ping Idefix eth1 (%s) from local computer : Success %s" % ('\n\n<b><span foreground="green">', test_ip, '</span></b> \n')
            else :
                message += "%s Ping Idefix eth1 (%s) from local computer : Failed %s" % ('\n\n<b><span foreground="red">', test_ip, '</span></b> \n')
            self.arw["network_summary_label3"].set_markup(message)



            self.controller.arw["network_summary_status"].set_text(_("Ping Idefix eth0 "))
            while Gtk.events_pending():
                Gtk.main_iteration()

            test_ip = network["idefix"]["eth0"]
            result = subprocess.check_output(["ping", "-n", "1", test_ip ]).decode("cp850")
            if "TTL" in result:
                message += "%s Ping Idefix eth0 (%s) from local computer : Success %s" % ('\n<b><span foreground="green">', test_ip, '</span></b> \n')
            else :
                message += "%s Ping Idefix eth0 (%s) from local computer : Failed %s" % ('\n<b><span foreground="red">', test_ip, '</span></b> \n')
            self.arw["network_summary_label3"].set_markup(message)



    def get_infos(self, command, result = "result", progress = False, json = False):
        # get infos from Idefix. The process is :
        #  - write a command in the 'trigger' file
        #  - the command is processed by Idefix, and the result is written in the 'result' file
        #  - the 'result' file is read, and data returned.
        #  - if json is set, then the data is first decoded
        #  - if progress is set, data is sent every second
        #  @spin : the spin object
        #  @ progress : a label object

        ftp1 = self.controller.ftp_config
        ftp = ftp_connect(ftp1["server"][0], ftp1["login"][0], ftp1["pass"][0])
        if not ftp:
            return False
        self.ftp = ftp

        command_f = io.BytesIO()
        ftp.storlines('STOR ' + result, command_f)       # delete data in result file

        command_f.write(bytes(command, "utf-8"))
        command_f.seek(0)
        # send command
        ftp.storlines('STOR trigger', command_f)

        # wait until Idefix has finished the job
        time1 = time.time()
        for i in range(60):     # set absolute maximum to 60 seconds
            while time.time() < time1 + i:
                while Gtk.events_pending():               # necessary to have the spinner work
                        Gtk.main_iteration()
            if progress:
                data1 = ftp_get(ftp, result)
                progress.set_markup(me(data1))

            status =  ftp_get(self.ftp, "trigger")
            if status == "ready":
                break

        data1 = ftp_get(ftp, result)
        ftp.close()
        return data1


    def idefix_infos(self, widget):
        self.arw['why_stack'].set_visible_child_name('page0')
        if isinstance(widget, str):
            action = widget
        else:
            action = widget.name

        if action == "linux_command":                                          # launched by the Go button
            command = "linux " + self.arw["linux_command_entry"].get_text()      # get command from the entry
        elif action == "infos_filter":
            if self.arw["infos_filter_dns"].get_active():
                command = "unbound"
            else:
                command = "squid"
        else:
            command = action.replace("infos_", "")

        if command in ["unbound", "squid", "mac", "all"]:
            display_label = self.arw["infos_label"]
            spinner = self.arw["infos_spinner"]
        else:
            display_label = self.arw["infos_label2"]
            spinner = self.arw["infos_spinner2"]
            self.arw["display2_stack"].set_visible_child(self.arw["infos_page2_1"])

        if command in["unbound", "squid"]:
            try:
                command += " " + self.controller.myip
            except:
                display_label.set_markup("ip not found. The command cannot be executed")
                return

        spinner.start()
        if command in ("versions"):
            result = self.get_infos(command, progress=display_label)
        elif command in("all"):
            result = self.get_infos(command, result='result.zip')
        else:
            result = self.get_infos(command)
        spinner.stop()

        if command == "all":
            dialog = ExportDiagnosticDialog(self.arw, self)
            dialog.run(result)
        else:
            # escape characters incompatible with pango markup
            result = me(result)

            # set colors
            if command.startswith("unbound"):
                result2 = result.split("\n")
                result3 = ""
                for line in result2:
                    if "no match" in line :
                        line = '<span foreground="blue">' + line.strip() + "</span>"
                    elif "denied" in line :
                        line = '<span foreground="red">' + line.strip() + "</span>"
                    elif "allowed" in line :
                        line = '<span foreground="green">' + line.strip() + "</span>"
                    if "validation failure" in line :
                        line = '<span background="#ff9999">' + me(line.strip()) + "</span>\n"
                    result3 += line + "\n"
                result = result3
            elif command == "mac":
                result2 = result.split("\n")
                result3 = ""
                for line in result2:
                    if "expired" in line :
                        line = '<span foreground="red">' + line.strip() + "</span>"
                    elif "active" in line :
                        line = '<span foreground="green">' + line.strip() + "</span>"
                    result3 += line +"\n"
                result = result3

            display_label.set_markup(result)

    def search(self, widget):
        self.arw['why_stack'].set_visible_child_name('page0')
        mac_search = self.arw["search_mac"].get_text().strip().lower()

        output1 = ""
        if mac_search != "":
            for user in self.controller.maclist:
                for mac in self.controller.maclist[user]:
                    if mac_search in mac:
                        output1 += user + " : " + mac + "\n"

        domain_search = self.arw["search_domain"].get_text().strip().lower()

        output = ""
        if domain_search != "":
            for group in self.controller.config['groups']:
                if domain_search in group:
                    output += _("group : %s \n") % (group)
                for domain in self.controller.config['groups'][group]['dest_domains']:
                    if domain_search in domain:
                        output += _("group : %s --> %s \n") % (group, domain)
            for rule in self.controller.config['rules']:
                if domain_search in rule:
                    output += _("rule : %s \n") % (rule)
                for domain in self.controller.config['rules'][rule]['dest_domains']:
                    if domain_search in domain:
                        output += _("rule : %s --> %s \n") % (rule, domain)

        self.arw["infos_label"].set_text(output1 + "\n\n" + output)


    def update_display(self, widget):
        self.arw['why_stack'].set_visible_child_name('page0')
        ftp1 = self.controller.ftp_config
        ftp = ftp_connect(ftp1["server"][0], ftp1["login"][0], ftp1["pass"][0])
        data1 = ftp_get(ftp, "result")
        self.arw["infos_label"].set_markup(data1)
        ftp.close()

    def check_permissions(self, widget):
        """Run the permissions check after the check permission dialog has been completed"""

        # Recreate the store
        self.arw['permission_user_store'].clear()
        for item in self.controller.users.users_store:
            for user in item.iterchildren():
                self.arw['permission_user_store'].append([user[0]])
                for subuser in user.iterchildren():
                    self.arw['permission_user_store'].append([subuser[0]])

        # Show the selection dialog
        dialog = self.arw['permission_check_dialog']
        response = dialog.run()

        dialog.hide()

        if response != Gtk.ResponseType.OK:
            return

        model, selected_iter = self.arw['permission_check_user'].get_selection().get_selected()

        if not model or not selected_iter:
            showwarning(_("No User Selected"), _("Please select a user"))
            return

        user = model.get_value(selected_iter, 0)

        domain = self.arw['permission_check_domain'].get_text()

        if not domain:
            showwarning(_("No Domain Entered"), _("Please enter a valid domain"))
            return

        self.arw['why_stack'].set_visible_child_name('why')

        config = json.loads(open("unbound.json").read(), object_pairs_hook=OrderedDict)

        self.arw['why_store'].clear()

        rule_info = self.is_allowed(user, domain, config)
        self.arw['why_info_label'].set_text(_("%s rules for %s") % (domain, user))

        for name, info in rule_info['rules'].items():

            rule_iter = self.arw['why_store'].append()
            self.arw['why_store'].set_value(rule_iter, WHY_COLUMN_NAME, name)

            # The domain is a list of matches to compare against the target domain
            # eg: ['com', 'microsoft', '*']  will match 'www.microsoft.com'
            # iterate through both target and rule domains looking for matches
            # if '*' is encountered then mark the rest of the domain as a pass
            # if a part of the domain doesn't match then mark the rest of the domain as fail

            rule_domain = iter(info.get('domain', []))
            domain_parts = []
            target_domain = reversed(domain.split('.'))

            while True:
                try:
                    source = rule_domain.__next__()
                except StopIteration:
                    source = ''

                try:
                    target = target_domain.__next__()
                except StopIteration:
                    break

                if source.lower() == target.lower():
                    domain_parts.append("<span foreground='green'>" + source + "</span>")
                    continue

                # Get the rest of the target
                parts = [target]
                while True:
                    try:
                        parts.append(target_domain.__next__())
                    except StopIteration:
                        break

                rest = '.'.join(reversed(parts))
                if source == '*':
                    # We match everything from here further down green
                    domain_parts.append("<span foreground='green'>" + rest + "</span>")
                else:
                    # This and everything below does not match and is red
                    domain_parts.append("<span foreground='red'>" + rest + "</span>")

            self.arw['why_store'].set_value(rule_iter, WHY_COLUMN_DOMAIN, '.'.join(reversed(domain_parts)))

            notes = ''
            if not info.get('user', True):
                notes += "<span foreground='red'>☹</span> "
            else:
                notes += "<span foreground='green'>☺</span> "

            if 'time_condition' in info:
                if not info.get('time_condition'):
                    notes += "<span foreground='red'>⏰</span> "
                else:
                    notes += "<span foreground='green'>⏰</span> "

            self.arw['why_store'].set_value(rule_iter, WHY_COLUMN_RULE_DISABLED, not info.get('enabled'))

            if not info.get('valid', True):
                self.arw['why_store'].set_value(rule_iter, WHY_COLUMN_RULE_INVALID, True)
                notes = info.get('reason')

            if 'action' in info:
                if info['action']:
                    self.arw['why_store'].set_value(rule_iter, WHY_COLUMN_RULE_TYPE, Gtk.STOCK_APPLY)
                else:
                    self.arw['why_store'].set_value(rule_iter, WHY_COLUMN_RULE_TYPE, Gtk.STOCK_CANCEL)
            else:
                self.arw['why_store'].set_value(rule_iter, WHY_COLUMN_RULE_TYPE, Gtk.STOCK_JUMP_TO)

            self.arw['why_store'].set_value(rule_iter, WHY_COLUMN_INFO, notes)

    """ File editor   """

    def edit_file(self, widget):

        self.arw["display2_stack"].set_visible_child(self.arw["infos_page2_2"])
        filename = widget.name.replace("file_", "")
        if filename == "eth0":
            full_path = "/etc/network/interfaces.d/eth0"
        elif filename == "eth1":
            full_path = "/etc/network/interfaces.d/eth1"
        elif filename == "idefix.conf":
            full_path = "/etc/idefix/idefix.conf"
        elif filename == "idefix2_conf":
            full_path = "/etc/idefix/idefix2_conf.json"
        elif filename == "ddclient.conf":
            full_path = "/etc/ddclient.conf"

        self.edited_file = full_path

        data1 = self.get_infos("linux cat " + full_path)
        self.arw["editor_textview"].get_buffer().set_text(data1)


    def save_file(self, widget):
        text_buffer = self.arw["editor_textview"].get_buffer()
        (start_iter, end_iter) = text_buffer.get_bounds()
        full_text = text_buffer.get_text(start_iter, end_iter, False)
        command_f = io.BytesIO()
        command_f.write(bytes(full_text, "utf-8")) #.replace(b'\r\n', b'\n'))
        ftp1 = self.controller.ftp_config
        ftp = ftp_connect(ftp1["server"][0], ftp1["login"][0], ftp1["pass"][0])
        command_f.seek(0)
        ftp.storbinary('STOR buffer', command_f)
        command_f = io.BytesIO()
        command_f.write(bytes("linux cp /home/rock64/idefix/buffer " + self.edited_file, "utf-8"))
        command_f.seek(0)
        ftp.storbinary('STOR trigger', command_f)


    def open_editor(self, widget):
        self.arw["informations_stack"].set_visible_child(self.arw["editor_box"])

    def close_editor(self, widget):
        self.arw["informations_stack"].set_visible_child(self.arw["informations_box"])

    def hide_network_summary(self, widget):
        self.arw["network_summary"].hide()

    def open_supervix(self, widget):
        if self.idefix_ip:
            os.startfile("http://%s:10080/visu-donnees-systeme.php" % self.idefix_ip)
        else:
            alert(_("Idefix was not found"))
