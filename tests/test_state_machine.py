from dashboard.python.detector.state_machine import TremorStateMachine

sm = TremorStateMachine()

scores = [
    20,
    25,
    82,
    81,
    80,
    83,
    82,
    40,
    30,
    25,
    20,
]

for s in scores:

    print(s, sm.update(s))

