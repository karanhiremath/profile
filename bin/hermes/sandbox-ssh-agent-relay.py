#!/usr/bin/env python3
"""Relay an ssh-agent into a Hermes podman sandbox without copying key material.

The identity a sandbox needs may live only in an agent (a 1Password agent, for
instance, never writes a private key to disk), so staging key files cannot
supply it. This relays the agent socket instead:

    sandbox ssh --IdentityAgent--> unix socket in container
        --> container mode: unix -> TCP host.containers.internal:PORT
            --> host mode:   TCP 127.0.0.1:PORT -> real agent socket

No private key ever enters the container, and revoking access is just stopping
the relay.

Host mode is deliberately a filtering proxy: only "list identities" and "sign"
requests are forwarded. A sandbox therefore cannot add, remove, or lock keys in
the operator's agent -- it can only ask for signatures. Everything else is
answered with SSH_AGENT_FAILURE.

Both sides are pure stdlib because neither the host nor the sandbox image ships
socat or netcat.
"""

from __future__ import annotations

import argparse
import os
import socket
import struct
import sys
import threading

# ssh-agent protocol message numbers (RFC 4251 framing: uint32 length, payload).
SSH_AGENTC_REQUEST_IDENTITIES = 11
SSH_AGENTC_SIGN_REQUEST = 13
SSH_AGENT_FAILURE = 5

ALLOWED_REQUESTS = frozenset({SSH_AGENTC_REQUEST_IDENTITIES, SSH_AGENTC_SIGN_REQUEST})

MAX_MESSAGE = 256 * 1024


def log(message: str) -> None:
    print(f"sandbox-ssh-agent-relay: {message}", file=sys.stderr, flush=True)


def recv_exactly(sock: socket.socket, count: int) -> bytes | None:
    chunks = []
    remaining = count
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_message(sock: socket.socket) -> bytes | None:
    header = recv_exactly(sock, 4)
    if header is None:
        return None
    (length,) = struct.unpack(">I", header)
    if length == 0 or length > MAX_MESSAGE:
        return None
    return recv_exactly(sock, length)


def write_message(sock: socket.socket, payload: bytes) -> None:
    sock.sendall(struct.pack(">I", len(payload)) + payload)


def serve_filtered(client: socket.socket, agent_path: str) -> None:
    """Forward only list/sign requests from one client to the real agent."""
    with client:
        while True:
            request = read_message(client)
            if request is None:
                return
            if request[0] not in ALLOWED_REQUESTS:
                log(f"rejected agent request type {request[0]}")
                try:
                    write_message(client, bytes([SSH_AGENT_FAILURE]))
                except OSError:
                    return
                continue
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as agent:
                    agent.connect(agent_path)
                    write_message(agent, request)
                    response = read_message(agent)
            except OSError as exc:
                log(f"agent connection failed: {exc}")
                try:
                    write_message(client, bytes([SSH_AGENT_FAILURE]))
                except OSError:
                    pass
                return
            if response is None:
                return
            try:
                write_message(client, response)
            except OSError:
                return


def pump(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(16384)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def serve_forward(client: socket.socket, host: str, port: int) -> None:
    """Splice one client onto the host-side TCP relay."""
    with client:
        try:
            upstream = socket.create_connection((host, port), timeout=10)
        except OSError as exc:
            log(f"upstream {host}:{port} unreachable: {exc}")
            return
        with upstream:
            threads = [
                threading.Thread(target=pump, args=(client, upstream), daemon=True),
                threading.Thread(target=pump, args=(upstream, client), daemon=True),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()


def run_host(agent_path: str, port: int, bind: str) -> int:
    if not os.path.exists(agent_path):
        log(f"agent socket not found: {agent_path}")
        return 1
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind((bind, port))
    except OSError as exc:
        log(f"cannot bind {bind}:{port}: {exc}")
        return 1
    listener.listen(16)
    log(f"host relay on {bind}:{port} -> {agent_path} (list/sign only)")
    with listener:
        while True:
            client, _ = listener.accept()
            threading.Thread(
                target=serve_filtered, args=(client, agent_path), daemon=True
            ).start()


def run_container(listen_path: str, host: str, port: int) -> int:
    parent = os.path.dirname(listen_path) or "."
    os.makedirs(parent, exist_ok=True)
    if os.path.exists(listen_path):
        os.unlink(listen_path)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(listen_path)
    # Only the agent user may talk to the relay socket.
    os.chmod(listen_path, 0o600)
    listener.listen(16)
    log(f"container relay on {listen_path} -> {host}:{port}")
    with listener:
        while True:
            client, _ = listener.accept()
            threading.Thread(
                target=serve_forward, args=(client, host, port), daemon=True
            ).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--mode", required=True, choices=("host", "container"),
        help="host: TCP -> real agent socket. container: unix socket -> host TCP.",
    )
    parser.add_argument("--agent-socket", default=os.environ.get("SSH_AUTH_SOCK", ""),
                        help="host mode: path of the real agent socket")
    parser.add_argument("--listen", default="/tmp/hermes-ssh-agent.sock",
                        help="container mode: unix socket path to create")
    parser.add_argument("--host", default="host.containers.internal",
                        help="container mode: host-relay address")
    parser.add_argument("--port", type=int, default=17352, help="relay TCP port")
    parser.add_argument("--bind", default="127.0.0.1",
                        help="host mode: bind address (loopback only by default)")
    args = parser.parse_args(argv)

    if args.mode == "host":
        if not args.agent_socket:
            log("no agent socket given and SSH_AUTH_SOCK is unset")
            return 1
        return run_host(args.agent_socket, args.port, args.bind)
    return run_container(args.listen, args.host, args.port)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
