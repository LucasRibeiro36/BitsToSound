from service.ClientService import ClientService 

while True:
    try:
        client_service = ClientService()
        print(client_service.receive_audio())
    except KeyboardInterrupt:
        print("Interrupted by user.")
        break