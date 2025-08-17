"""
World manager for dynamic chunk loading and unloading, now with mesh batching.
"""
import math
import threading
import queue
import time
import numpy as np
from collections import defaultdict
from world.chunk import Chunk
from engine.mesh_batch import MeshBatch
from config.settings import CHUNK_SIZE, RENDER_DISTANCE, PRELOAD_DISTANCE, UNLOAD_DISTANCE, MAX_CHUNKS
import logging

class WorldManager:
    def __init__(self):
        logging.info("Initializing WorldManager...")
        self.chunks = {}
        self.last_player_chunk = (None, None)
        self.max_chunks = MAX_CHUNKS

        self.mesh_batch = None # Lazy initialization
        
        self.chunk_queue = queue.Queue()
        self.completed_chunks = queue.Queue()
        self.generating_chunks = set()
        self.generation_threads = []
        self.stop_generation = False
        
        self.num_threads = min(4, max(2, threading.active_count() // 2))
        
        self.priority_queue = queue.PriorityQueue()
        self.use_priority_queue = True
        
        self.max_chunks_per_frame = 3
        self.frame_budget_ms = 3.0

        self.chunks_to_build_mesh = queue.Queue()
        self.max_mesh_builds_per_frame = 10

        self.last_camera_direction = np.array([0, 0, -1], dtype=np.float32)
        self.last_camera_position = np.array([0, 0, 0], dtype=np.float32)
        
        self.start_generation_threads()
        logging.info("WorldManager initialized.")
        
    def _get_mesh_batch(self):
        if self.mesh_batch is None:
            logging.info("Initializing MeshBatch lazily.")
            self.mesh_batch = MeshBatch()
        return self.mesh_batch

    def start_generation_threads(self):
        for i in range(self.num_threads):
            thread = threading.Thread(target=self._chunk_generation_worker, daemon=True)
            thread.start()
            self.generation_threads.append(thread)
    
    def _chunk_generation_worker(self):
        while not self.stop_generation:
            try:
                priority, chunk_coords = self.priority_queue.get(timeout=0.1)
                if chunk_coords in self.chunks or chunk_coords in self.generating_chunks:
                    continue
                
                chunk = Chunk(chunk_coords[0], chunk_coords[1])
                self.completed_chunks.put((chunk_coords, chunk))
                self.generating_chunks.discard(chunk_coords)
            except queue.Empty:
                continue

    def process_completed_chunks(self):
        for _ in range(self.max_chunks_per_frame):
            try:
                chunk_coords, chunk = self.completed_chunks.get_nowait()
                if len(self.chunks) < self.max_chunks:
                    self.chunks[chunk_coords] = chunk
                    logging.info(f"Chunk {chunk_coords} loaded, adding to mesh build queue.")
                    self.chunks_to_build_mesh.put(chunk)
            except queue.Empty:
                break

    def process_mesh_builds(self):
        for _ in range(self.max_mesh_builds_per_frame):
            try:
                chunk = self.chunks_to_build_mesh.get_nowait()
                if chunk.needs_update:
                    logging.info(f"Building mesh for chunk ({chunk.x}, {chunk.z})")
                    vertex_data = chunk.build_mesh()
                    if vertex_data is not None:
                        logging.info(f"Adding {len(vertex_data)} vertices from chunk ({chunk.x}, {chunk.z}) to mesh batch.")
                        chunk.mesh_handle = self._get_mesh_batch().add_mesh(vertex_data)
                    else:
                        logging.info(f"Chunk ({chunk.x}, {chunk.z}) produced no vertices.")
            except queue.Empty:
                break
    
    def update(self, camera_position, camera_front):
        self.last_camera_position[:] = camera_position
        self.last_camera_direction[:] = camera_front
        
        self.process_completed_chunks()
        self.process_mesh_builds()
        
        player_chunk_x, player_chunk_z = self.get_chunk_coords(camera_position[0], camera_position[2])
        if (player_chunk_x, player_chunk_z) != self.last_player_chunk:
            self.last_player_chunk = (player_chunk_x, player_chunk_z)
            self.load_surrounding_chunks(player_chunk_x, player_chunk_z)
            self.unload_distant_chunks(player_chunk_x, player_chunk_z)
        
        if self.mesh_batch:
            self.mesh_batch.update_buffer()

    def load_surrounding_chunks(self, player_chunk_x, player_chunk_z):
        logging.info(f"Loading surrounding chunks for player at ({player_chunk_x}, {player_chunk_z})")
        for radius in range(PRELOAD_DISTANCE + 1):
            for dx in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    if max(abs(dx), abs(dz)) != radius:
                        continue

                    chunk_x, chunk_z = player_chunk_x + dx, player_chunk_z + dz
                    if (chunk_x, chunk_z) not in self.chunks and (chunk_x, chunk_z) not in self.generating_chunks:
                        priority = self.calculate_chunk_priority(chunk_x, chunk_z, player_chunk_x, player_chunk_z)
                        self.generating_chunks.add((chunk_x, chunk_z))
                        self.priority_queue.put((priority, (chunk_x, chunk_z)))

    def unload_distant_chunks(self, player_chunk_x, player_chunk_z):
        chunks_to_remove = [
            key for key, chunk in self.chunks.items()
            if max(abs(key[0] - player_chunk_x), abs(key[1] - player_chunk_z)) > UNLOAD_DISTANCE
        ]
        if chunks_to_remove:
            logging.info(f"Unloading {len(chunks_to_remove)} distant chunks.")
        for key in chunks_to_remove:
            del self.chunks[key]

    def calculate_chunk_priority(self, chunk_x, chunk_z, player_chunk_x, player_chunk_z):
        dx, dz = chunk_x - player_chunk_x, chunk_z - player_chunk_z
        distance = math.sqrt(dx*dx + dz*dz)
        chunk_dir = np.array([dx, 0, dz], dtype=np.float32)
        norm = np.linalg.norm(chunk_dir)
        if norm > 0:
            chunk_dir /= norm
        view_alignment = np.dot(chunk_dir, np.array([self.last_camera_direction[0], 0, self.last_camera_direction[2]]))
        if view_alignment > 0.5:
            distance *= 0.5
        return distance

    def render_world(self):
        # logging.info("Rendering world...")
        if self.mesh_batch:
            self.mesh_batch.render()

    def get_chunk_coords(self, world_x, world_z):
        return math.floor(world_x / CHUNK_SIZE), math.floor(world_z / CHUNK_SIZE)

    def cleanup(self):
        logging.info("Cleaning up WorldManager...")
        self.stop_generation = True
        for thread in self.generation_threads:
            thread.join(timeout=1.0)
        if self.mesh_batch:
            self.mesh_batch.cleanup()
        self.chunks.clear()
        logging.info("WorldManager cleaned up.")

    def load_initial_chunks(self, camera_position):
        player_chunk_x, player_chunk_z = self.get_chunk_coords(camera_position[0], camera_position[2])
        self.load_surrounding_chunks(player_chunk_x, player_chunk_z)