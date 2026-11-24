TASKS related "<text>" [--deps <id,id>] # run before every add; --deps
                                        # also lists their umbrellas
TASKS show <id> [--raw]                 # --raw: {key.field} unresolved
TASKS delete <id>
TASKS verify <id> "<how the children met the goal>"   # close an umbrella
TASKS note <id> [--at "<step>"] "<what the work did not predict>"
            [--date YYYY-MM-DD]         # Note (<date>): …; any status but
                                        # proposed/not-planned, done included
TASKS inputs <id> "<input>=<value>; …"  # Inputs: …, the values a run was
                                        # given (never a live {key.field})
TASKS distilled <sitting> "<T3-T7, T9>" # tasks whose every candidate the
                                        # user has dealt with; stays open
TASKS ran <id> [--flow <name[,name]>] --record "<inputs; deviations>"
               [--date <date|timestamp>]   # close an ops task with its run record;
                                        # on a distill sitting also records
                                        # it and its dependents as distilled
