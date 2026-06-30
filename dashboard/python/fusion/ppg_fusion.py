class PPGFusion:

    def process(self, ir, red):

        return {

            "ir": ir,

            "red": red,

            "finger_detected": ir > 5000

        }
