TASKS --scope <subdir> <subcommand> ...
TASKS init [--name <handle>] [--scope <subdir>] [--integration <branch>]
           [--parent <branch>] [--iteration N] [--iteration-name <name>]
           [--iteration-started YYYY-MM-DD]
TASKS whoami [--role]                   # your handle (the roster handle your
                                        # GitHub login holds); --role:
                                        # integrator | contributor
TASKS config [<key> [<value>]]          # parent_branch, iteration,
                                        # iteration_name, iteration_started
TASKS contributor list | rm <name>      # rm: yourself, or anyone as integrator
      | rename <name> <new-name>       # same rule; the old handle stays reserved
