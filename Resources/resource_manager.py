import psutil


class ResourceManager:

    def __init__(self, state):
        self.state = state

    def update(self):

        self.state.cpu_load = psutil.cpu_percent(interval=None)

        self.state.ram_load = psutil.virtual_memory().percent

        # Пока GPU позже
        self.state.gpu_load = 0

        if self.state.cpu_load > 95 or self.state.ram_load > 95:
            self.state.energy -= 1
        else:
            self.state.energy = min(100, self.state.energy + 0.1)