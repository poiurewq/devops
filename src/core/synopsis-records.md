TASKS related "<text>" [--deps <id,id>] # run before every add; --deps
                                        # also lists their umbrellas
TASKS show <id>
TASKS delete <id>
TASKS verify <id> "<how the children met the goal>"   # close an umbrella
TASKS note <id> [--at "<step>"] "<what the work did not predict>"
            [--date YYYY-MM-DD]         # Note (<date>): …; any status but
                                        # proposed/not-planned, done included
TASKS ran <id> [--flow <name[,name]>] --record "<inputs; deviations>"
               [--date <date|timestamp>]   # close an ops task with its run record
