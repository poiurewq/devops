TASKS flow list [--all] [--json] | show <name> [--raw] | runs <name> [--json]
      | create <new-name> --desc "<one line>" [--inputs "<a, b (hint)>"]
           [--uses "<flow, flow>"] [--body T | --file F]
      | update <name> [--desc] [--inputs] [--uses] [--status active|retired]
           [--body T | --file F] [--append "<paragraph>"]   # --append repeats,
                                                            # one paragraph each, in order
      | rename <name> <new-name> | retire <name>     # names, never numbers
      | reid <name>                  # only when two boards minted one id
TASKS agent list [--json] | show <name> [--raw] | rm <name>
      | rename <name> <new-name>     # a former name stays reserved
      | add <name> --accessors "<handle, handle>" --desc "<who it is>"
      | update <name> [--accessors "<handle, …>"] [--desc]
TASKS env list [--json] | show <name> [--raw] | rm <name>
      | rename <name> <new-name>
      | add <name> --accessors "<handle, handle>" [--machine M]
           [--expects "<prose>"]
      | update <name> [--accessors] [--machine M|""] [--expects]
TASKS routine list [--json] | show <name> [--raw] | rm <name>
      | rename <name> <new-name>
      | add <name> --accessors "<handle, handle>"
           --mode attended|unattended --environment <env>
           --schedule "<cron> <timezone>"|<timestamp> --trigger "<what, where>"
           --manage "<how to change or remove it there>"
      | update <name> [--accessors] [--mode] [--environment] [--schedule]
           [--trigger] [--manage] [--status active|paused]
      | wake <name>                  # exit 2 + reason, else its due tasks
TASKS catalog list [<category>] [--json] | show <key> [--raw] | rm <key>
      | get <key>.<field>[.<field>…]  # the value a reference resolves to
      | add <category> <key> [--set "<field>=<value>"]…   # --set repeats
      | update <key> --set "<field>=<value>"…            # empty value clears
      | rename <key> <new-name>      # a former name stays reserved
      | category add <category> --field "<field>: <what it holds>[ (one of: a, b)]"…
      | category update <category> [--field "…"]… [--drop-field <field>]…
      | category show <category> | category rm <category>
      | category rename <category> <new-name>
