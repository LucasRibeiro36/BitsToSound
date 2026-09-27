from service.ClientService import ClientService


def main() -> None:
    client_service = ClientService()
    print("Listening for packets. Press Ctrl+C to stop.")

    try:
        while True:
            event = client_service.receive_event(timeout_seconds=None)
            if event is None:
                continue

            event_type = event.get("type")
            if event_type == "chat":
                print(f"[CHAT] node {event.get('src')}: {event.get('text')}")
            elif event_type == "ping":
                print(f"[PING] node {event.get('src')}: {event.get('text')}")
            elif event_type == "pong":
                print(f"[PONG] node {event.get('src')}: {event.get('text')}")
            elif event_type == "file_meta":
                print(
                    f"[FILE] receiving transfer {event.get('transfer_id')} ({event.get('filename')})"
                )
            elif event_type == "file_saved":
                print(f"[FILE] saved at {event.get('filename')}")
            elif event_type == "file_error":
                print(f"[FILE] error for {event.get('filename')}: {event.get('reason')}")
            else:
                print(event)
    except KeyboardInterrupt:
        print("Interrupted by user.")


if __name__ == "__main__":
    main()
