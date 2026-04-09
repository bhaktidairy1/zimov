import binascii

def hex_recv(sock, expect_len=4096, label=None) -> bytes:
    data = sock.recv(expect_len)
    if not data:
        raise ConnectionError("Server closed connection")
    h = binascii.hexlify(data).decode()
    if label:
        print(f"← {label} ({len(data)} bytes): {h}")
    else:
        print(f"← Received ({len(data)} bytes): {h}")
    return data

def hex_send(sock, hexstr: str, label=None):
    hexstr = hexstr.replace(" ", "")
    raw = binascii.unhexlify(hexstr)
    sock.sendall(raw)
    if label:
        print(f"→ {label}: {hexstr}")
    else:
        print(f"→ Sent: {hexstr}")
