from service.ServerService import ServerService


def main() -> None:
    server_service = ServerService()

    print("Commands: chat <message> | ping [message] | file <absolute_or_relative_path> | quit")
    while True:
        command = input("> ").strip()
        if not command:
            continue

        if command == "quit":
            break

        if command.startswith("chat "):
            message = command[5:]
            success = server_service.send_chat(message)
            print("chat sent" if success else "chat failed")
            continue

        if command.startswith("ping"):
            payload = command[5:] if len(command) > 4 else "ping"
            success = server_service.send_ping(payload.strip() or "ping")
            print("ping sent" if success else "ping failed")
            continue

        if command.startswith("file "):
            file_path = command[5:].strip()
            try:
                success = server_service.send_file(file_path)
                print("file sent" if success else "file failed")
            except FileNotFoundError as exc:
                print(exc)
            continue

        print("Unknown command")


if __name__ == "__main__":
    main()
