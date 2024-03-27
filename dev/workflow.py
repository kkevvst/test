from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os

from ansible import constants as C
C.DEFAULT_LOG_PATH = '/Users/hua/github/ansible/mytest/ansible.log'
# C.DEFAULT_DEBUG = True
from ansible import context
from ansible.cli import CLI
from ansible.cli.arguments import optparse_helpers as opt_help
from ansible.errors import AnsibleParserError
from ansible.module_utils._text import to_text, to_native
from ansible.module_utils.parsing.convert_bool import boolean
from ansible.playbook.play import Play
from ansible.playbook.playbook_include import PlaybookInclude
from ansible.plugins.loader import add_all_plugin_dirs
from ansible.utils.display import Display
from ansible.parsing.dataloader import DataLoader
from ansible.inventory.manager import InventoryManager
from ansible.vars.manager import VariableManager
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.utils.ssh_functions import check_for_controlpersist
from ansible.plugins.loader import become_loader, connection_loader, shell_loader
from ansible.template import Templar
from ansible.utils.helpers import pct_to_int
from ansible.utils.path import makedirs_safe

display = Display()


__all__ = ['Workflow']

# lib/ansible/executor/playbook_executor.py  PlaybookExecutor
class Workflow:

    def __init__(self, loader):
        # Entries in the datastructure of a playbook may
        # be either a play or an include statement
        self._jobs = {}
        self._workflows = []
        self._vars = None
        self._basedir = to_text(os.getcwd(), errors='surrogate_or_strict')
        self._loader = loader
        self._file_name = None

    @staticmethod
    def _play_prereqs():
        options = context.CLIARGS

        # all needs loader
        loader = DataLoader()

        basedir = options.get('basedir', False)
        if basedir:
            loader.set_basedir(basedir)
            add_all_plugin_dirs(basedir)

        # create the inventory, and filter it based on the subset specified (if any)
        inventory = InventoryManager(loader=loader, sources='/Users/hua/github/ansible/mytest/hosts')

        # create the variable manager, which will be shared throughout
        # the code, ensuring a consistent view of global variables
        variable_manager = VariableManager(loader=loader, inventory=inventory)

        return loader, inventory, variable_manager

    @staticmethod
    def load(file_name, variable_manager=None, loader=None):
        wf = Workflow(loader=loader)
        wf._load_workflow_data(file_name=file_name, variable_manager=variable_manager)
        return wf

    def _load_workflow_data(self, file_name, variable_manager, vars=None):

        if os.path.isabs(file_name):
            self._basedir = os.path.dirname(file_name)
        else:
            self._basedir = os.path.normpath(os.path.join(self._basedir, os.path.dirname(file_name)))

        # set the loaders basedir
        cur_basedir = self._loader.get_basedir()
        self._loader.set_basedir(self._basedir)

        add_all_plugin_dirs(self._basedir)

        self._file_name = file_name

        try:
            ds = self._loader.load_from_file(os.path.basename(file_name))
        except UnicodeDecodeError as e:
            raise AnsibleParserError("Could not read playbook (%s) due to encoding issues: %s" % (file_name, to_native(e)))

        # check for errors and restore the basedir in case this error is caught and handled
        if ds is None:
            self._loader.set_basedir(cur_basedir)
            raise AnsibleParserError("Empty workflow, nothing to do", obj=ds)
        elif not isinstance(ds, dict):
            self._loader.set_basedir(cur_basedir)
            raise AnsibleParserError("A workflow must be a dictionary, got a %s instead" % type(ds), obj=ds)
        elif not ds:
            display.deprecated("Empty workflow will currently be skipped, in the future they will cause a syntax error", version='2.12')

        # Parse the playbook entries. For plays, we simply parse them
        # using the Play() object, and includes are parsed using the
        # PlaybookInclude() object
        # for entry in ds:
        #     if not isinstance(entry, dict):
        #         # restore the basedir in case this error is caught and handled
        #         self._loader.set_basedir(cur_basedir)
        #         raise AnsibleParserError("playbook entries must be either a valid play or an include statement", obj=entry)

        #     if any(action in entry for action in ('import_playbook', 'include')):
        #         if 'include' in entry:
        #             display.deprecated("'include' for playbook includes. You should use 'import_playbook' instead", version="2.12")
        #         pb = PlaybookInclude.load(entry, basedir=self._basedir, variable_manager=variable_manager, loader=self._loader)
        #         if pb is not None:
        #             self._entries.extend(pb._entries)
        #         else:
        #             which = entry.get('import_playbook', entry.get('include', entry))
        #             display.display("skipping playbook '%s' due to conditional test failure" % which, color=C.COLOR_SKIP)
        #     else:
        #         entry_obj = Play.load(entry, variable_manager=variable_manager, loader=self._loader, vars=vars)
        #         self._entries.append(entry_obj)
        for entry in ds:
            print(entry)
            if entry == 'jobs':
                for job in ds[entry]:
                    # print(job)
                    self._jobs[job] = (ds[entry][job])
            elif entry == 'workflows':
                for workflow in ds[entry]:
                    if isinstance(ds[entry][workflow], dict):
                        self._workflows.append(ds[entry][workflow])
            elif entry == 'parameters':
                self._vars = ds[entry]
            else:
                raise Exception("Unknown entry type: %s" % entry)

        # we're done, so restore the old basedir in the loader
        self._loader.set_basedir(cur_basedir)

    def get_loader(self):
        return self._loader

    def get_jobs(self):
        return self._jobs
    
    def get_workflows(self):
        return self._workflows[:]
    
    def get_vars(self):
        return self._vars
    
    def get_pipeline(self):
        pipeline = []
        workflows = self.get_workflows()
        for workflow in workflows:
            jobs = workflow.get('jobs', [])
            for job in jobs:
                if isinstance(job, str):
                    pipeline.append({job: {"requires": []}})
                elif isinstance(job, dict):
                    pipeline.append(job)
                else:
                    raise Exception("Unknown job type: %s" % type(job))
        return pipeline

class PlaysExecutor:

    '''
    This is the primary class for executing playbooks, and thus the
    basis for bin/ansible-playbook operation.
    '''

    def __init__(self, playbooks, inventory, variable_manager, loader, passwords):
        self._playbooks = playbooks
        self._inventory = inventory
        self._variable_manager = variable_manager
        self._loader = loader
        self.passwords = passwords
        self._unreachable_hosts = dict()

        if context.CLIARGS.get('listhosts') or context.CLIARGS.get('listtasks') or \
                context.CLIARGS.get('listtags') or context.CLIARGS.get('syntax'):
            self._tqm = None
        else:
            self._tqm = TaskQueueManager(
                inventory=inventory,
                variable_manager=variable_manager,
                loader=loader,
                passwords=self.passwords,
                forks=context.CLIARGS.get('forks'),
            )

        # Note: We run this here to cache whether the default ansible ssh
        # executable supports control persist.  Sometime in the future we may
        # need to enhance this to check that ansible_ssh_executable specified
        # in inventory is also cached.  We can't do this caching at the point
        # where it is used (in task_executor) because that is post-fork and
        # therefore would be discarded after every task.
        check_for_controlpersist(C.ANSIBLE_SSH_EXECUTABLE)

    def run(self):
        '''
        Run the given playbook, based on the settings in the play which
        may limit the runs to serialized groups, etc.
        '''

        result = 0
        entrylist = []
        entry = {}
        try:
            # preload become/connection/shell to set config defs cached
            list(connection_loader.all(class_only=True))
            list(shell_loader.all(class_only=True))
            list(become_loader.all(class_only=True))

            for play in self._playbooks:
                # pb = Playbook.load(playbook_path, variable_manager=self._variable_manager, loader=self._loader)
                # FIXME: move out of inventory self._inventory.set_playbook_basedir(os.path.realpath(os.path.dirname(playbook_path)))

                if self._tqm is None:  # we are doing a listing
                    entry['plays'] = []
                else:
                    # make sure the tqm has callbacks loaded
                    self._tqm.load_callbacks()
                    # self._tqm.send_callback('v2_playbook_on_start', pb)

                i = 1

                if play._included_path is not None:
                    self._loader.set_basedir(play._included_path)
                else:
                    self._loader.set_basedir('.')

                # clear any filters which may have been applied to the inventory
                self._inventory.remove_restriction()

                # Allow variables to be used in vars_prompt fields.
                all_vars = self._variable_manager.get_vars(play=play)
                templar = Templar(loader=self._loader, variables=all_vars)
                setattr(play, 'vars_prompt', templar.template(play.vars_prompt))

                # FIXME: this should be a play 'sub object' like loop_control
                if play.vars_prompt:
                    for var in play.vars_prompt:
                        vname = var['name']
                        prompt = var.get("prompt", vname)
                        default = var.get("default", None)
                        private = boolean(var.get("private", True))
                        confirm = boolean(var.get("confirm", False))
                        encrypt = var.get("encrypt", None)
                        salt_size = var.get("salt_size", None)
                        salt = var.get("salt", None)
                        unsafe = var.get("unsafe", None)

                        if vname not in self._variable_manager.extra_vars:
                            if self._tqm:
                                self._tqm.send_callback('v2_playbook_on_vars_prompt', vname, private, prompt, encrypt, confirm, salt_size, salt,
                                                        default, unsafe)
                                play.vars[vname] = display.do_var_prompt(vname, private, prompt, encrypt, confirm, salt_size, salt, default, unsafe)
                            else:  # we are either in --list-<option> or syntax check
                                play.vars[vname] = default

                # Post validate so any play level variables are templated
                all_vars = self._variable_manager.get_vars(play=play)
                templar = Templar(loader=self._loader, variables=all_vars)
                play.post_validate(templar)

                # if context.CLIARGS['syntax']:
                #     continue

                if self._tqm is None:
                    # we are just doing a listing
                    entry['plays'].append(play)

                else:
                    self._tqm._unreachable_hosts.update(self._unreachable_hosts)

                    previously_failed = len(self._tqm._failed_hosts)
                    previously_unreachable = len(self._tqm._unreachable_hosts)

                    break_play = False
                    # we are actually running plays
                    batches = self._get_serialized_batches(play)
                    if len(batches) == 0:
                        self._tqm.send_callback('v2_playbook_on_play_start', play)
                        self._tqm.send_callback('v2_playbook_on_no_hosts_matched')
                    for batch in batches:
                        # restrict the inventory to the hosts in the serialized batch
                        self._inventory.restrict_to_hosts(batch)
                        # and run it...
                        result = self._tqm.run(play=play)

                        # break the play if the result equals the special return code
                        if result & self._tqm.RUN_FAILED_BREAK_PLAY != 0:
                            result = self._tqm.RUN_FAILED_HOSTS
                            break_play = True

                        # check the number of failures here, to see if they're above the maximum
                        # failure percentage allowed, or if any errors are fatal. If either of those
                        # conditions are met, we break out, otherwise we only break out if the entire
                        # batch failed
                        failed_hosts_count = len(self._tqm._failed_hosts) + len(self._tqm._unreachable_hosts) - \
                            (previously_failed + previously_unreachable)

                        if len(batch) == failed_hosts_count:
                            break_play = True
                            break

                        # update the previous counts so they don't accumulate incorrectly
                        # over multiple serial batches
                        previously_failed += len(self._tqm._failed_hosts) - previously_failed
                        previously_unreachable += len(self._tqm._unreachable_hosts) - previously_unreachable

                        # save the unreachable hosts from this batch
                        self._unreachable_hosts.update(self._tqm._unreachable_hosts)

                    if break_play:
                        break

                i = i + 1  # per play

                if entry:
                    entrylist.append(entry)  # per playbook

                # send the stats callback for this playbook
                if self._tqm is not None:
                    self._tqm.send_callback('v2_playbook_on_stats', self._tqm._stats)

                # if the last result wasn't zero, break out of the playbook file name loop
                if result != 0:
                    break

            if entrylist:
                return entrylist

        finally:
            if self._tqm is not None:
                self._tqm.cleanup()
            if self._loader:
                self._loader.cleanup_all_tmp_files()

        return result

    def _get_serialized_batches(self, play):
        '''
        Returns a list of hosts, subdivided into batches based on
        the serial size specified in the play.
        '''

        # make sure we have a unique list of hosts
        all_hosts = self._inventory.get_hosts(play.hosts, order=play.order)
        all_hosts_len = len(all_hosts)

        # the serial value can be listed as a scalar or a list of
        # scalars, so we make sure it's a list here
        serial_batch_list = play.serial
        if len(serial_batch_list) == 0:
            serial_batch_list = [-1]

        cur_item = 0
        serialized_batches = []

        while len(all_hosts) > 0:
            # get the serial value from current item in the list
            serial = pct_to_int(serial_batch_list[cur_item], all_hosts_len)

            # if the serial count was not specified or is invalid, default to
            # a list of all hosts, otherwise grab a chunk of the hosts equal
            # to the current serial item size
            if serial <= 0:
                serialized_batches.append(all_hosts)
                break
            else:
                play_hosts = []
                for x in range(serial):
                    if len(all_hosts) > 0:
                        play_hosts.append(all_hosts.pop(0))

                serialized_batches.append(play_hosts)

            # increment the current batch list item number, and if we've hit
            # the end keep using the last element until we've consumed all of
            # the hosts in the inventory
            cur_item += 1
            if cur_item > len(serial_batch_list) - 1:
                cur_item = len(serial_batch_list) - 1

        return serialized_batches


class MyCLI(CLI):
    def init_parser(self):
        super(MyCLI, self).init_parser()
        opt_help.add_connect_options(self.parser)
        opt_help.add_meta_options(self.parser)
        opt_help.add_runas_options(self.parser)
        opt_help.add_subset_options(self.parser)
        opt_help.add_check_options(self.parser)
        opt_help.add_inventory_options(self.parser)
        opt_help.add_runtask_options(self.parser)
        opt_help.add_vault_options(self.parser)
        opt_help.add_fork_options(self.parser)
        opt_help.add_module_options(self.parser)

        # ansible playbook specific opts
        self.parser.add_option('--list-tasks', dest='listtasks', action='store_true',
                               help="list all tasks that would be executed")
        self.parser.add_option('--list-tags', dest='listtags', action='store_true',
                               help="list all available tags")
        self.parser.add_option('--step', dest='step', action='store_true',
                               help="one-step-at-a-time: confirm each task before running")
        self.parser.add_option('--start-at-task', dest='start_at_task',
                               help="start the playbook at the task matching this name")

    def post_process_args(self, options, args):
        options, args = super(MyCLI, self).post_process_args(options, args)

        display.verbosity = options.verbosity
        self.validate_conflicts(options, runas_opts=True, vault_opts=True, fork_opts=True)

        return options, args
    
    def run(self):
        super(MyCLI, self).run()
        loader, inventory, variable_manager = Workflow._play_prereqs()
        wf = Workflow.load(loader=loader, file_name=self.args[0])#args[0]
        pipeline = wf.get_pipeline()
        jobs = wf.get_jobs()
        vars = wf.get_vars()
        entries = []
        
        for job in pipeline:
            for name, value in job.items(): # name: job name, value: requires list
                print(name)
                print(value)
                if jobs[name]: # playbook job
                    # print(jobs[name])
                    entry_obj = Play.load(jobs[name][0], variable_manager=variable_manager, loader=loader, vars=vars)
                    entries.append(entry_obj)

        playsexe = PlaysExecutor(entries, inventory, variable_manager, loader, passwords=None)
        result = playsexe.run()


if __name__ == '__main__':
    pipe_file='/Users/hua/github/ansible/mytest/workflow.yml'
    args = [pipe_file, '-v']
    # C.DEFAULT_DEBUG = True
    
    cli = MyCLI(args)
    cli.run()
    # loader, inventory, variable_manager = Workflow._play_prereqs()
    # wf = Workflow.load(loader=loader, file_name='/Users/hua/github/ansible/mytest/workflow.yml')
    # pipeline = wf.get_pipeline()
    # jobs = wf.get_jobs()
    # vars = wf.get_vars()
    # entries = []
    # # vars = None
    
    # for job in pipeline:
    #     for name, value in job.items(): # name: job name, value: requires list
    #         print(name)
    #         print(value)
    #         if jobs[name]: # playbook job
    #             # print(jobs[name])
    #             entry_obj = Play.load(jobs[name][0], variable_manager=variable_manager, loader=loader, vars=vars)
    #             entries.append(entry_obj)

    # playsexe = PlaysExecutor(entries, inventory, variable_manager, loader, passwords=None)
    # result = playsexe.run()
    # print(result)

