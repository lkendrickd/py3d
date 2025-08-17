"""
World manager for dynamic chunk loading and unloading - FULLY FIXED VERSION.
"""
import math
import threading
import queue
import time
import numpy as np
from collections import defaultdict
from world.chunk import Chunk
from config.settings import CHUNK_SIZE, RENDER_DISTANCE, PRELOAD_DISTANCE, UNLOAD_DISTANCE, MAX_CHUNKS


class WorldManager:
    def __init__(self):
        self.chunks = {}  # Dictionary to store loaded chunks (x, z) -> Chunk
        self.last_player_chunk = (None, None)  # Last chunk position of player

        self.max_chunks = MAX_CHUNKS
        
        # Threading for chunk generation
        self.chunk_queue = queue.Queue()  # Queue for chunks to generate
        self.completed_chunks = queue.Queue()  # Queue for completed chunks with their mesh data
        self.generating_chunks = set()  # Set of chunk coords currently being generated
        self.generation_threads = []
        self.stop_generation = False
        
        # Use multiple threads for better performance
        self.num_threads = min(4, max(2, threading.active_count() // 2))  # 2-4 threads
        
        # Priority system for chunk generation
        self.priority_queue = queue.PriorityQueue()  # (priority, chunk_coords)
        self.use_priority_queue = True
        
        # Performance tracking
        self.chunks_generated_this_frame = 0
        self.max_chunks_per_frame = 3
        self.frame_budget_ms = 5.0  # Generous budget for uploading meshes
        self.last_process_time = 0

        # Deferred operations queues
        self.chunks_to_cleanup = []
        self.max_cleanups_per_frame = 5

        # Camera tracking for prioritization
        self.last_camera_direction = np.array([0, 0, -1], dtype=np.float32)
        self.last_camera_position = np.array([0, 0, 0], dtype=np.float32)

        # Stats tracking
        self.chunks_in_view_direction = set()
        self.generation_stats = {
            'total_generated': 0,
            'total_cleaned': 0,
            'meshes_built': 0
        }
        
        # Start chunk generation threads
        self.start_generation_threads()
        
    def start_generation_threads(self):
        """Start background threads for chunk generation and meshing"""
        print(f"Starting {self.num_threads} chunk generation threads...")
        for i in range(self.num_threads):
            thread = threading.Thread(target=self._chunk_generation_worker, daemon=True)
            thread.start()
            self.generation_threads.append(thread)
        print(f"Chunk generation threads started successfully")
    
    def _chunk_generation_worker(self):
        """Worker thread for generating chunks and building their meshes in the background"""
        while not self.stop_generation:
            chunk_coords = None
            try:
                # Try priority queue first, then regular queue
                if self.use_priority_queue:
                    try:
                        _, chunk_coords = self.priority_queue.get(timeout=0.05)
                    except queue.Empty:
                        try:
                            chunk_coords = self.chunk_queue.get(timeout=0.05)
                        except queue.Empty:
                            continue
                else:
                    chunk_coords = self.chunk_queue.get(timeout=0.1)
                
                chunk_x, chunk_z = chunk_coords
                
                if chunk_coords in self.chunks:
                    self.generating_chunks.discard(chunk_coords)
                    continue

                # Generate the chunk data
                chunk = Chunk(chunk_x, chunk_z)
                
                # Build the mesh data (CPU intensive)
                vertex_data = chunk.build_mesh()

                # Put completed chunk and its mesh data in the completed queue
                self.completed_chunks.put((chunk_coords, chunk, vertex_data))
                
                self.generating_chunks.discard(chunk_coords)
                self.generation_stats['total_generated'] += 1
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error generating chunk {chunk_coords}: {e}")
                if chunk_coords is not None:
                    self.generating_chunks.discard(chunk_coords)
    
    def process_completed_chunks(self):
        """Process completed chunks from the generation threads, uploading their meshes to the GPU"""
        start_time = time.time() * 1000
        chunks_added = 0
        
        while chunks_added < self.max_chunks_per_frame:
            if time.time() * 1000 - start_time > self.frame_budget_ms:
                break
            
            try:
                chunk_coords, chunk, vertex_data = self.completed_chunks.get_nowait()

                if len(self.chunks) >= self.max_chunks:
                    self.force_cleanup_furthest_chunks(5)
                
                # Upload the mesh data to the GPU (this happens on the main thread)
                chunk.upload_mesh(vertex_data)
                self.generation_stats['meshes_built'] += 1

                # Add the fully processed chunk to the world
                self.chunks[chunk_coords] = chunk
                chunks_added += 1
                self.chunks_generated_this_frame += 1
                
            except queue.Empty:
                break
        
        self.last_process_time = time.time() * 1000 - start_time
        return chunks_added

    def process_chunk_cleanups(self):
        """Process chunk cleanups in batches"""
        if not self.chunks_to_cleanup:
            return 0

        cleanups_to_process = min(len(self.chunks_to_cleanup), self.max_cleanups_per_frame)
        for _ in range(cleanups_to_process):
            if self.chunks_to_cleanup:
                chunk = self.chunks_to_cleanup.pop(0)
                chunk.cleanup()
                self.generation_stats['total_cleaned'] += 1

        return cleanups_to_process

    def force_cleanup_furthest_chunks(self, count):
        """Force cleanup of furthest chunks when at capacity"""
        if not self.last_camera_position.any():
            return

        player_chunk_x, player_chunk_z = self.get_chunk_coords(
            self.last_camera_position[0],
            self.last_camera_position[2]
        )

        chunk_distances = []
        for (chunk_x, chunk_z), chunk in self.chunks.items():
            distance = max(abs(chunk_x - player_chunk_x), abs(chunk_z - player_chunk_z))
            chunk_distances.append((distance, (chunk_x, chunk_z)))

        chunk_distances.sort(reverse=True)

        removed = 0
        for _, coords in chunk_distances[:count]:
            if coords in self.chunks:
                chunk = self.chunks.pop(coords)
                chunk.cleanup()
                removed += 1
                self.generation_stats['total_cleaned'] += 1

        if removed > 0:
            print(f"Force cleaned {removed} furthest chunks (capacity management)")

    def calculate_chunk_priority(self, chunk_x, chunk_z, player_chunk_x, player_chunk_z):
        """Calculate priority based on distance AND view direction"""
        dx = chunk_x - player_chunk_x
        dz = chunk_z - player_chunk_z
        distance = math.sqrt(dx*dx + dz*dz)

        if abs(self.last_camera_direction[0]) > 0.1 or abs(self.last_camera_direction[2]) > 0.1:
            chunk_dir = np.array([dx, 0, dz], dtype=np.float32)
            norm = np.linalg.norm(chunk_dir)
            if norm > 0:
                chunk_dir /= norm
                view_alignment = np.dot(chunk_dir, np.array([self.last_camera_direction[0], 0, self.last_camera_direction[2]]))
                if view_alignment > 0.5:
                    distance *= 0.5
                    self.chunks_in_view_direction.add((chunk_x, chunk_z))
                elif view_alignment < -0.5:
                    distance *= 2.0
        return distance
    
    def request_chunk_generation(self, chunk_x, chunk_z, priority=None):
        """Request a chunk to be generated asynchronously"""
        chunk_coords = (chunk_x, chunk_z)
        if chunk_coords in self.chunks or chunk_coords in self.generating_chunks:
            return False
        
        if len(self.chunks) + len(self.generating_chunks) > self.max_chunks * 1.2:
            return False

        self.generating_chunks.add(chunk_coords)
        if priority is not None and self.use_priority_queue:
            self.priority_queue.put((priority, chunk_coords))
        else:
            self.chunk_queue.put(chunk_coords)
        return True
        
    def get_chunk_coords(self, world_x, world_z):
        """Convert world coordinates to chunk coordinates"""
        return math.floor(world_x / CHUNK_SIZE), math.floor(world_z / CHUNK_SIZE)
    
    def get_chunk(self, chunk_x, chunk_z):
        """Get a chunk if it exists"""
        return self.chunks.get((chunk_x, chunk_z))
    
    def load_initial_chunks(self, camera_position):
        """Load initial chunks around camera position synchronously"""
        player_chunk_x, player_chunk_z = self.get_chunk_coords(camera_position[0], camera_position[2])
        print(f"Pre-generating world around chunk ({player_chunk_x}, {player_chunk_z})...")
        
        immediate_radius = 3
        chunks_loaded = 0
        print("Phase 1: Loading and meshing immediate chunks synchronously...")
        for dx in range(-immediate_radius, immediate_radius + 1):
            for dz in range(-immediate_radius, immediate_radius + 1):
                chunk_x, chunk_z = player_chunk_x + dx, player_chunk_z + dz
                key = (chunk_x, chunk_z)
                if key not in self.chunks:
                    chunk = Chunk(chunk_x, chunk_z)
                    vertex_data = chunk.build_mesh()
                    chunk.upload_mesh(vertex_data)
                    self.chunks[key] = chunk
                    chunks_loaded += 1
        print(f"Phase 1 complete: {chunks_loaded} immediate chunks loaded and meshed")
        
        print("Phase 2: Queuing nearby chunks for background generation...")
        chunks_queued = 0
        for radius in range(immediate_radius + 1, PRELOAD_DISTANCE + 1):
            for dx in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    if max(abs(dx), abs(dz)) == radius:
                        chunk_x, chunk_z = player_chunk_x + dx, player_chunk_z + dz
                        priority = radius
                        if self.request_chunk_generation(chunk_x, chunk_z, priority):
                            chunks_queued += 1
        
        print(f"Phase 2 complete: {chunks_queued} chunks queued")
        print(f"Initial setup: {chunks_loaded} immediate + {chunks_queued} queued")
        
        self.last_player_chunk = (player_chunk_x, player_chunk_z)
        return chunks_loaded
    
    def unload_distant_chunks(self, player_chunk_x, player_chunk_z):
        """Queue distant chunks for cleanup"""
        chunks_to_remove = [
            key for key, chunk in self.chunks.items()
            if max(abs(key[0] - player_chunk_x), abs(key[1] - player_chunk_z)) > UNLOAD_DISTANCE
        ]
        
        for key in chunks_to_remove:
            chunk = self.chunks.pop(key)
            self.chunks_to_cleanup.append(chunk)
        
        if chunks_to_remove:
            print(f"Queued {len(chunks_to_remove)} chunks for cleanup (beyond distance {UNLOAD_DISTANCE})")
        return len(chunks_to_remove)
    
    def update(self, camera_position, camera_front=None):
        """Update world based on camera position and direction"""
        self.last_camera_position = np.array(camera_position, dtype=np.float32)
        if camera_front is not None:
            self.last_camera_direction = np.array(camera_front, dtype=np.float32)

        self.chunks_generated_this_frame = 0
        self.chunks_in_view_direction.clear()
        
        self.process_chunk_cleanups()
        self.process_completed_chunks()
        
        player_chunk_x, player_chunk_z = self.get_chunk_coords(camera_position[0], camera_position[2])
        
        if (player_chunk_x, player_chunk_z) != self.last_player_chunk:
            print(f"Player moved to chunk ({player_chunk_x}, {player_chunk_z})")
            self.last_player_chunk = (player_chunk_x, player_chunk_z)
            
            chunks_requested = 0
            max_requests_per_update = 20
            
            # Simplified request loop
            for radius in range(1, PRELOAD_DISTANCE + 1):
                if chunks_requested >= max_requests_per_update:
                    break
                for dx in range(-radius, radius + 1):
                    for dz in range(-radius, radius + 1):
                        if chunks_requested >= max_requests_per_update:
                            break
                        if max(abs(dx), abs(dz)) == radius:
                            chunk_x, chunk_z = player_chunk_x + dx, player_chunk_z + dz
                            priority = self.calculate_chunk_priority(chunk_x, chunk_z, player_chunk_x, player_chunk_z)
                            if self.request_chunk_generation(chunk_x, chunk_z, priority):
                                chunks_requested += 1
            
            if chunks_requested > 0:
                print(f"Requested {chunks_requested} new chunks (view-aware priority)")
            
            self.unload_distant_chunks(player_chunk_x, player_chunk_z)
            
            if len(self.chunks) > self.max_chunks:
                self.force_cleanup_furthest_chunks(len(self.chunks) - self.max_chunks + 10)
            
            print(f"Chunks: {len(self.chunks)} loaded, {len(self.generating_chunks)} generating, {self.completed_chunks.qsize()} awaiting upload")
    
    def get_visible_chunks(self, camera_position):
        """Get chunks that should be rendered"""
        player_chunk_x, player_chunk_z = self.get_chunk_coords(camera_position[0], camera_position[2])
        
        visible_chunks = [
            chunk for (cx, cz), chunk in self.chunks.items()
            if max(abs(cx - player_chunk_x), abs(cz - player_chunk_z)) <= RENDER_DISTANCE
            and not chunk.needs_update and chunk.vertex_count > 0
        ]

        visible_chunks.sort(key=lambda c: max(abs(c.x - player_chunk_x), abs(c.z - player_chunk_z)))
        return visible_chunks
    
    def cleanup(self):
        """Clean up all chunks and stop generation threads"""
        print("\nShutting down...")
        self.stop_generation = True
        for thread in self.generation_threads:
            thread.join(timeout=1.0)
        
        for chunk in self.chunks.values():
            chunk.cleanup()
        self.chunks.clear()

        for chunk in self.chunks_to_cleanup:
            chunk.cleanup()
        self.chunks_to_cleanup.clear()

        print(f"Cleanup stats: Generated {self.generation_stats['total_generated']}, "
              f"Cleaned {self.generation_stats['total_cleaned']}, "
              f"Meshes built {self.generation_stats['meshes_built']}")