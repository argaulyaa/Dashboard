import asyncio
import queue
import threading

import paramiko
from fastapi import WebSocket, WebSocketDisconnect

READ_CHUNK = 4096


def _open_channel(host: str, port: int, username: str, password: str):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=username,
        password=password,
        timeout=10,
        banner_timeout=10,
    )
    channel = client.invoke_shell(term="xterm-256color")
    channel.settimeout(0.0)
    return client, channel


def _reader_thread(channel, out_queue, stop_event):
    while not stop_event.is_set():
        try:
            if channel.recv_ready():
                data = channel.recv(READ_CHUNK)
                if not data:
                    break
                out_queue.put(data)
            else:
                stop_event.wait(0.05)
            if channel.closed:
                break
        except Exception:
            break
    out_queue.put(None)


async def run_ssh_bridge(ws: WebSocket, host: str, port: int, username: str, password: str):
    try:
        client, channel = await asyncio.get_event_loop().run_in_executor(
            None, _open_channel, host, port, username, password
        )
    except Exception as e:
        await ws.send_text(f"\r\n[gagal konek SSH: {e}]\r\n")
        await ws.close()
        return

    out_queue = queue.Queue()
    stop_event = threading.Event()
    reader = threading.Thread(target=_reader_thread, args=(channel, out_queue, stop_event), daemon=True)
    reader.start()

    async def pump_ssh_to_ws():
        loop = asyncio.get_event_loop()
        while True:
            data = await loop.run_in_executor(None, out_queue.get)
            if data is None:
                break
            try:
                await ws.send_text(data.decode(errors="replace"))
            except Exception:
                break

    pump_task = asyncio.create_task(pump_ssh_to_ws())

    try:
        while True:
            msg = await ws.receive_text()
            if msg.startswith("{"):
                import json
                try:
                    payload = json.loads(msg)
                    if payload.get("type") == "resize":
                        channel.resize_pty(width=payload["cols"], height=payload["rows"])
                        continue
                except Exception:
                    pass
            channel.send(msg)
    except WebSocketDisconnect:
        pass
    finally:
        stop_event.set()
        pump_task.cancel()
        try:
            channel.close()
            client.close()
        except Exception:
            pass