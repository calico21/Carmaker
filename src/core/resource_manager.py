import multiprocessing
import logging
import queue
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class ResourceManager:
    """
    Thread-safe & Process-safe manager for limited system resources.
    handles:
      1. TCP Ports (Unique required per instance)
      2. Licenses (Hard limit on concurrency)
    """
    def __init__(self, start_port: int, max_licenses: int):
        self.manager = multiprocessing.Manager()
        
        # A Queue acts as the pool of available ports.
        # FIFO (First-In-First-Out) ensures fair usage.
        self.available_ports = self.manager.Queue()
        
        # Populate the queue with ports (e.g., 16660 to 16660 + max_licenses)
        for i in range(max_licenses):
            self.available_ports.put(start_port + i)
            
        # A Semaphore strictly limits the number of active workers.
        # If max_licenses=4, the 5th worker will block here until one finishes.
        self.license_semaphore = self.manager.Semaphore(max_licenses)
        
        self.max_licenses = max_licenses
        logger.info(f"Resource Manager initialized with {max_licenses} slots.")

    @contextmanager
    def lease(self, worker_id: str):
        """
        Context Manager for safe resource allocation.
        Usage:
            with resource_manager.lease("Worker_1") as port:
                run_simulation(port)
        """
        port = None
        start_wait = time.time()
        
        try:
            # 1. Acquire License (Blocks if limit reached)
            # This is the "Throttle"
            logger.debug(f"[{worker_id}] Waiting for license...")
            self.license_semaphore.acquire()
            
            # 2. Acquire Port (Should be instant if semaphore passed)
            try:
                port = self.available_ports.get(timeout=5)
            except queue.Empty:
                # This indicates a logic error: Semaphore let us in, but no port?
                logger.critical(f"[{worker_id}] CRITICAL: License acquired but no Port available!")
                raise ResourceWarning("Port Pool Exhaustion")

            wait_time = time.time() - start_wait
            logger.info(f"[{worker_id}] Acquired License + Port {port} (Waited {wait_time:.2f}s)")
            
            yield port

        finally:
            # 3. Release Resources (Guaranteed execution even if simulation crashes)
            if port is not None:
                self.available_ports.put(port)
                logger.debug(f"[{worker_id}] Port {port} returned.")
            
            self.license_semaphore.release()
            logger.debug(f"[{worker_id}] License released.")