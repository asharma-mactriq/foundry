class CommandService:
    def handle(self, cmd):
        print("[Command]", cmd)

        action = cmd.get("action")
        if action == "start":
            print("[Device] START")
        elif action == "stop":
            print("[Device] STOP")

command_service = CommandService()
