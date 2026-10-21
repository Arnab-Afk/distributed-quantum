"""Exercise real libp2p transport using loopback sockets and temporary storage."""

from __future__ import annotations

import json
import time
from queue import Empty, SimpleQueue

from quantum_backend_v2.config import Libp2pSettings
from quantum_backend_v2.discovery.service import LibP2pNetworkThread
from quantum_backend_v2.libp2p import create_real_libp2p_runtime


def test_local_peers_exchange_rpc_and_discovery_then_stop(tmp_path):
    protocol = "/qmesh/transport-test/1.0.0"

    async def reply(payload: bytes) -> bytes:
        return b"ack:" + payload

    threads = []
    runtimes = []
    queues = []
    try:
        for label in ("a", "b"):
            settings = Libp2pSettings(
                peer_id=f"qmesh-transport-test-{label}",
                peerstore_path=tmp_path / f"{label}.sqlite3",
                listen_multiaddrs=("/ip4/127.0.0.1/tcp/0",),
                activate_listeners=True,
                bootstrap_peers=(),
                dev_service_peer_count=0,
                rendezvous_namespace="qmesh-transport-test",
                heartbeat_interval_seconds=5,
            )
            runtime = create_real_libp2p_runtime(settings)
            events = SimpleQueue()
            thread = LibP2pNetworkThread(
                settings, runtime, events, service_ids=(), request_handlers={protocol: reply}
            )
            runtimes.append(runtime)
            queues.append(events)
            threads.append(thread)
            thread.start()
            assert thread.is_running
            addresses = tuple(str(addr) for addr in runtime.host.get_addrs())
            assert addresses
            assert all(addr.startswith("/ip4/127.0.0.1/tcp/") for addr in addresses)
            assert all("/tcp/0/" not in addr for addr in addresses)

        for source, target in ((0, 1), (1, 0)):
            destination = runtimes[target].host
            payload = f"peer-{source}-to-{target}".encode()
            response = threads[source].request_bytes(
                peer_id=str(destination.get_id()),
                protocol_id=protocol,
                payload=payload,
                peer_addresses=tuple(str(addr) for addr in destination.get_addrs()),
                timeout_seconds=10,
            )
            assert response == b"ack:" + payload

        received = [False, False]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not all(received):
            for index, events in enumerate(queues):
                try:
                    event = events.get_nowait()
                except Empty:
                    continue
                if json.loads(event.raw_payload)["peer_id"] == str(
                    runtimes[1 - index].host.get_id()
                ):
                    received[index] = True
            time.sleep(0.1)
        assert all(received), f"Cross-peer discovery delivery: {received}"
    finally:
        for thread in reversed(threads):
            thread.stop()
        for runtime in runtimes:
            runtime.peerstore.close()
    assert all(not thread.is_running for thread in threads)
