from service.ServerService import ServerService

server_service = ServerService()

while True:
    message = input("Enter a message to transmit: ")
    byte_data = message.encode("utf-8")
    server_service.transmit_audio(byte_data)
