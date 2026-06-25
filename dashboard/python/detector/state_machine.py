"""
ParkinSense V2
Temporal Tremor State Machine
"""


class TremorStateMachine:

    NO_TREMOR = "NO_TREMOR"
    POSSIBLE = "POSSIBLE_TREMOR"
    CONFIRMED = "CONFIRMED_TREMOR"
    RECOVERY = "RECOVERY"

    def __init__(self):

        self.state = self.NO_TREMOR

        self.high_count = 0
        self.low_count = 0

    def update(self, score):

        HIGH = 75
        LOW = 55

        if score >= HIGH:

            self.high_count += 1
            self.low_count = 0

        elif score <= LOW:

            self.low_count += 1
            self.high_count = 0

        if self.state == self.NO_TREMOR:

            if self.high_count >= 2:
                self.state = self.POSSIBLE

        elif self.state == self.POSSIBLE:

            if self.high_count >= 4:
                self.state = self.CONFIRMED

            elif self.low_count >= 2:
                self.state = self.NO_TREMOR

        elif self.state == self.CONFIRMED:

            if self.low_count >= 2:
                self.state = self.RECOVERY

        elif self.state == self.RECOVERY:

            if self.low_count >= 4:
                self.state = self.NO_TREMOR

            elif self.high_count >= 2:
                self.state = self.CONFIRMED

        return {

            "state": self.state,

            "confirmed":

                self.state == self.CONFIRMED,

            "possible":

                self.state == self.POSSIBLE,

            "recovery":

                self.state == self.RECOVERY,

            "high_count": self.high_count,

            "low_count": self.low_count

        }
