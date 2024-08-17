import xpressNet

class MockHornbyController:
    def __init__(self):
        self.trains = {}  # Track states of all trains
        self.accessories = {}  # Track states of all accessories

    def get_train(self, train_number):
        if train_number not in self.trains:
            self.trains[train_number] = self.Train(train_number)
        return self.trains[train_number]

    def get_accessory(self, accessory_number):
        if accessory_number not in self.accessories:
            self.accessories[accessory_number] = {"direction": None}
        return self.accessories[accessory_number]

    def throttle(self, train_number, speed, direction):
        train = self.get_train(train_number)
        return train.throttle(speed, direction)

    def stop(self, train_number):
        train = self.get_train(train_number)
        return train.stop()

    def function(self, train_number, function_id, switch):
        train = self.get_train(train_number)
        return train.function(function_id, switch)

    def accessory(self, accessory_number, direction):
        accessory = self.get_accessory(accessory_number)
        accessory["direction"] = direction
        return {
            "status_code": 200,
            "message": "Mock accessory command executed",
            "data": {
                "accessory_number": accessory_number,
                "direction": direction
            }
        }

    class Train:
        def __init__(self, train_number):
            self.train_number = train_number
            self.speed = 0
            self.direction = xpressNet.FORWARD
            self.functions = {f'{i}': False for i in range(29)}  # Functions F0 to F28

        def throttle(self, speed, direction):
            self.speed = speed
            self.direction = direction
            return self.getState()

        def stop(self):
            self.speed = 0
            return self.getState()

        def function(self, function_id, switch):
            if 0 <= function_id <= 28:
                self.functions[f'{function_id}'] = bool(switch)
                return self.getState()
            else:
                return {
                    "status_code": 400,
                    "message": "Invalid function ID",
                    "data": self.getState()
                }

        def getState(self):
            return {
                "status_code": 200,
                "message": "Train state retrieved",
                "data": {
                    "train_number": self.train_number,
                    "speed": self.speed,
                    "direction": self.direction,
                    "functions": self.functions
                }
            }