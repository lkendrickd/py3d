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
        self.completed_chunks = queue.Queue()  # Queue for completed chunks
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
        self.max_chunks_per_frame = 3  # FIX: Increased from 1
        self.frame_budget_ms = 3.0  # FIX: Increased from 2ms
        self.last_process_time = 0

        # Deferred operations queues
        self.chunks_to_cleanup = []  # FIX: Use list for batch cleanup
        self.chunks_to_build_mesh = queue.Queue()  # Chunks needing mesh building
        self.max_cleanups_per_frame = 5  # FIX: Increased
        self.max_mesh_builds_per_frame = 8  # FIX: Significantly increased from 2

        # FIX: Track camera direction for prioritization
        self.last_camera_direction = np.array([0, 0, -1], dtype=np.float32)
        self.last_camera_position = np.array([0, 0, 0], dtype=np.float32)

        # FIX: Track chunk generation stats
        self.chunks_in_view_direction = set()
        self.generation_stats = {
            'total_generated': 0,
            'total_cleaned': 0,
            'meshes_built': 0
        }
        
        # Start chunk generation threads
        self.start_generation_threads()
        
    def start_generation_threads(self):
        """Start background threads for chunk generation"""
        print(f"Starting {self.num_threads} chunk generation threads...")
        for i in range(self.num_threads):
            thread = threading.Thread(target=self._chunk_generation_worker, daemon=True)
            thread.start()
            self.generation_threads.append(thread)
        print(f"Chunk generation threads started successfully")
    
    def _chunk_generation_worker(self):
        """Worker thread for generating chunks in the background"""
        while not self.stop_generation:
            chunk_coords = None
            try:
                # Try priority queue first, then regular queue
                if self.use_priority_queue:
                    try:
                        priority, chunk_coords = self.priority_queue.get(timeout=0.05)
                    except queue.Empty:
                        try:
                            chunk_coords = self.chunk_queue.get(timeout=0.05)
                        except queue.Empty:
                            continue
                else:
                    chunk_coords = self.chunk_queue.get(timeout=0.1)
                
                chunk_x, chunk_z = chunk_coords
                
                # Skip if already exists (race condition check)
                if chunk_coords in self.chunks:
                    self.generating_chunks.discard(chunk_coords)
                    continue

                # Generate the chunk (this is the expensive operation)
                chunk = Chunk(chunk_x, chunk_z)
                chunk.needs_update = True
                
                # Put completed chunk in the completed queue
                self.completed_chunks.put((chunk_coords, chunk))
                
                # Remove from generating set
                self.generating_chunks.discard(chunk_coords)
                self.generation_stats['total_generated'] += 1
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error generating chunk {chunk_coords}: {e}")
                if chunk_coords is not None:
                    self.generating_chunks.discard(chunk_coords)
    
    def process_completed_chunks(self):
        """Process completed chunks from the generation threads with time budget"""
        start_time = time.time() * 1000  # Convert to milliseconds
        
        chunks_added = 0
        max_chunks = self.max_chunks_per_frame
        
        # Process chunks but respect time budget
        while chunks_added < max_chunks:
            # Check if we've exceeded our time budget
            current_time = time.time() * 1000
            if current_time - start_time > self.frame_budget_ms:
                break
            
            try:
                chunk_coords, chunk = self.completed_chunks.get_nowait()

                # FIX: Check if we're at max capacity
                if len(self.chunks) >= self.max_chunks:
                    # Force cleanup of furthest chunks
                    self.force_cleanup_furthest_chunks(5)
                
                self.chunks[chunk_coords] = chunk
                
                # Queue mesh building with priority for chunks in view direction
                if chunk_coords in self.chunks_in_view_direction:
                    # Put at front of queue (hacky but works)
                    temp_queue = queue.Queue()
                    temp_queue.put(chunk)
                    while not self.chunks_to_build_mesh.empty():
                        temp_queue.put(self.chunks_to_build_mesh.get())
                    self.chunks_to_build_mesh = temp_queue
                else:
                    self.chunks_to_build_mesh.put(chunk)

                chunks_added += 1
                self.chunks_generated_this_frame += 1
                
            except queue.Empty:
                break
        
        self.last_process_time = time.time() * 1000 - start_time
        return chunks_added

    def process_mesh_builds(self):
        """Process mesh builds more aggressively"""
        builds_processed = 0
        max_builds = self.max_mesh_builds_per_frame
        
        start_time = time.time() * 1000
        time_budget = 5.0  # FIX: Increased budget for mesh building
        
        while builds_processed < max_builds:
            # Check time budget
            if time.time() * 1000 - start_time > time_budget:
                break

            try:
                chunk = self.chunks_to_build_mesh.get_nowait()
                if chunk.needs_update:
                    chunk.build_mesh()
                    self.generation_stats['meshes_built'] += 1
                builds_processed += 1
            except queue.Empty:
                break

        return builds_processed

    def process_chunk_cleanups(self):
        """Process chunk cleanups in batches"""
        if not self.chunks_to_cleanup:
            return 0

        # FIX: Process multiple cleanups at once
        cleanups_to_process = min(len(self.chunks_to_cleanup), self.max_cleanups_per_frame)

        for _ in range(cleanups_to_process):
            if self.chunks_to_cleanup:
                chunk = self.chunks_to_cleanup.pop(0)
                chunk.cleanup()
                self.generation_stats['total_cleaned'] += 1

        return cleanups_to_process

    def force_cleanup_furthest_chunks(self, count):
        """FIX: Force cleanup of furthest chunks when at capacity"""
        if not self.last_camera_position.any():
            return

        player_chunk_x, player_chunk_z = self.get_chunk_coords(
            self.last_camera_position[0],
            self.last_camera_position[2]
        )

        # Calculate distances and sort
        chunk_distances = []
        for (chunk_x, chunk_z), chunk in self.chunks.items():
            distance = max(abs(chunk_x - player_chunk_x), abs(chunk_z - player_chunk_z))
            chunk_distances.append((distance, (chunk_x, chunk_z), chunk))

        # Sort by distance (furthest first)
        chunk_distances.sort(reverse=True)

        # Remove furthest chunks
        removed = 0
        for distance, coords, chunk in chunk_distances[:count]:
            if coords in self.chunks:
                chunk.cleanup()
                del self.chunks[coords]
                removed += 1
                self.generation_stats['total_cleaned'] += 1

        if removed > 0:
            print(f"Force cleaned {removed} furthest chunks (capacity management)")

    def calculate_chunk_priority(self, chunk_x, chunk_z, player_chunk_x, player_chunk_z):
        """FIX: Calculate priority based on distance AND view direction"""
        dx = chunk_x - player_chunk_x
        dz = chunk_z - player_chunk_z

        # Base distance priority
        distance = math.sqrt(dx*dx + dz*dz)

        # Check if chunk is in view direction
        if abs(self.last_camera_direction[0]) > 0.1 or abs(self.last_camera_direction[2]) > 0.1:
            chunk_dir = np.array([dx, 0, dz], dtype=np.float32)
            if np.linalg.norm(chunk_dir) > 0:
                chunk_dir = chunk_dir / np.linalg.norm(chunk_dir)

                # Calculate dot product with camera direction
                view_alignment = np.dot(chunk_dir,
                                       np.array([self.last_camera_direction[0], 0, self.last_camera_direction[2]]))

                # Prioritize chunks in front of camera
                if view_alignment > 0.5:  # In front
                    distance *= 0.5  # Higher priority (lower number)
                    self.chunks_in_view_direction.add((chunk_x, chunk_z))
                elif view_alignment < -0.5:  # Behind
                    distance *= 2.0  # Lower priority

        return distance
    
    def request_chunk_generation(self, chunk_x, chunk_z, priority=None):
        """Request a chunk to be generated asynchronously with optional priority"""
        chunk_coords = (chunk_x, chunk_z)
        
        # Don't generate if already exists or is being generated
        if chunk_coords in self.chunks or chunk_coords in self.generating_chunks:
            return False
        
        # FIX: Don't generate if we're way over capacity
        if len(self.chunks) + len(self.generating_chunks) > self.max_chunks * 1.2:
            return False

        # Add to generation queue
        self.generating_chunks.add(chunk_coords)
        
        # Use priority queue if priority is specified
        if priority is not None and self.use_priority_queue:
            self.priority_queue.put((priority, chunk_coords))
        else:
            self.chunk_queue.put(chunk_coords)
        return True
        
    def get_chunk_coords(self, world_x, world_z):
        """Convert world coordinates to chunk coordinates"""
        chunk_x = math.floor(world_x / CHUNK_SIZE)
        chunk_z = math.floor(world_z / CHUNK_SIZE)
        return chunk_x, chunk_z
    
    def get_chunk(self, chunk_x, chunk_z):
        """Get a chunk if it exists"""
        key = (chunk_x, chunk_z)
        return self.chunks.get(key, None)
    
    def load_initial_chunks(self, camera_position):
        """Load initial chunks around camera position"""
        player_chunk_x, player_chunk_z = self.get_chunk_coords(camera_position[0], camera_position[2])
        
        print(f"Pre-generating world around chunk ({player_chunk_x}, {player_chunk_z})...")
        
        # Phase 1: Load immediate chunks synchronously
        immediate_radius = 3  # FIX: Slightly larger for better initial experience
        chunks_loaded = 0
        
        print("Phase 1: Loading immediate chunks synchronously...")
        for dx in range(-immediate_radius, immediate_radius + 1):
            for dz in range(-immediate_radius, immediate_radius + 1):
                chunk_x = player_chunk_x + dx
                chunk_z = player_chunk_z + dz
                key = (chunk_x, chunk_z)
                
                if key not in self.chunks:
                    # Load these initial chunks synchronously for immediate gameplay
                    chunk = Chunk(chunk_x, chunk_z)
                    self.chunks[key] = chunk
                    self.chunks_to_build_mesh.put(chunk)
                    chunks_loaded += 1
        
        print(f"Phase 1 complete: {chunks_loaded} immediate chunks loaded")
        
        # Phase 2: Queue nearby chunks for background generation
        print("Phase 2: Queuing chunks for background generation...")
        chunks_queued = 0
        
        # Generate chunks in rings, prioritizing closer ones
        for radius in range(immediate_radius + 1, PRELOAD_DISTANCE + 1):
            for dx in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    # Only generate chunks on the edge of this radius
                    if max(abs(dx), abs(dz)) == radius:
                        chunk_x = player_chunk_x + dx
                        chunk_z = player_chunk_z + dz
                        
                        priority = radius  # Closer = higher priority (lower number)
                        if self.request_chunk_generation(chunk_x, chunk_z, priority):
                            chunks_queued += 1
        
        print(f"Phase 2 complete: {chunks_queued} chunks queued")
        print(f"Initial setup: {chunks_loaded} immediate + {chunks_queued} queued")
        
        self.last_player_chunk = (player_chunk_x, player_chunk_z)
        return chunks_loaded
    
    def unload_distant_chunks(self, player_chunk_x, player_chunk_z):
        """Queue distant chunks for cleanup"""
        chunks_to_remove = []
        
        # FIX: Use a proper unload distance that's larger than render distance
        actual_unload_distance = UNLOAD_DISTANCE

        for (chunk_x, chunk_z), chunk in self.chunks.items():
            distance = max(abs(chunk_x - player_chunk_x), abs(chunk_z - player_chunk_z))
            if distance > actual_unload_distance:
                chunks_to_remove.append((chunk_x, chunk_z))
        
        # Queue chunks for cleanup
        for key in chunks_to_remove:
            chunk = self.chunks[key]
            self.chunks_to_cleanup.append(chunk)
            del self.chunks[key]
        
        if chunks_to_remove:
            print(f"Queued {len(chunks_to_remove)} chunks for cleanup (beyond distance {actual_unload_distance})")

        return len(chunks_to_remove)
    
    def update(self, camera_position, camera_front=None):
        """Update world based on camera position and direction"""
        # Update camera tracking
        self.last_camera_position = np.array(camera_position, dtype=np.float32)
        if camera_front is not None:
            self.last_camera_direction = np.array(camera_front, dtype=np.float32)

        # Reset frame counter
        self.chunks_generated_this_frame = 0
        self.chunks_in_view_direction.clear()
        
        # Process deferred operations
        cleanups = self.process_chunk_cleanups()
        mesh_builds = self.process_mesh_builds()

        # Process completed chunks
        completed = self.process_completed_chunks()
        
        # Get player's current chunk
        player_chunk_x, player_chunk_z = self.get_chunk_coords(camera_position[0], camera_position[2])
        
        # Check if player moved to a different chunk
        if (player_chunk_x, player_chunk_z) != self.last_player_chunk:
            print(f"Player moved to chunk ({player_chunk_x}, {player_chunk_z})")
            self.last_player_chunk = (player_chunk_x, player_chunk_z)
            
            # FIX: Request chunks with view direction priority
            chunks_requested = 0
            max_requests_per_update = 20  # FIX: More aggressive loading
            
            # First pass: prioritize view direction
            view_forward = self.last_camera_direction
            for distance in range(1, RENDER_DISTANCE + 3):
                if chunks_requested >= max_requests_per_update // 2:
                    break

                # Calculate chunk position in view direction
                chunk_offset_x = int(view_forward[0] * distance)
                chunk_offset_z = int(view_forward[2] * distance)
                
                # Check a cone in view direction
                for dx in range(-distance//2, distance//2 + 1):
                    for dz in range(-distance//2, distance//2 + 1):
                        chunk_x = player_chunk_x + chunk_offset_x + dx
                        chunk_z = player_chunk_z + chunk_offset_z + dz

                        priority = self.calculate_chunk_priority(
                            chunk_x, chunk_z, player_chunk_x, player_chunk_z
                        )

                        if self.request_chunk_generation(chunk_x, chunk_z, priority):
                            chunks_requested += 1
                            if chunks_requested >= max_requests_per_update // 2:
                                break

            # Second pass: fill in gaps around player
            for radius in range(1, PRELOAD_DISTANCE):
                if chunks_requested >= max_requests_per_update:
                    break
                    
                for dx in range(-radius, radius + 1):
                    for dz in range(-radius, radius + 1):
                        if chunks_requested >= max_requests_per_update:
                            break
                            
                        if max(abs(dx), abs(dz)) == radius:
                            chunk_x = player_chunk_x + dx
                            chunk_z = player_chunk_z + dz
                            
                            priority = self.calculate_chunk_priority(
                                chunk_x, chunk_z, player_chunk_x, player_chunk_z
                            )

                            if self.request_chunk_generation(chunk_x, chunk_z, priority):
                                chunks_requested += 1
            
            if chunks_requested > 0:
                print(f"Requested {chunks_requested} new chunks (view-aware priority)")
            
            # Unload distant chunks
            unloaded = self.unload_distant_chunks(player_chunk_x, player_chunk_z)
            
            # FIX: Force cleanup if we have too many chunks
            if len(self.chunks) > self.max_chunks:
                over_limit = len(self.chunks) - self.max_chunks
                self.force_cleanup_furthest_chunks(over_limit + 10)
            
            print(f"Chunks: {len(self.chunks)} loaded, {len(self.generating_chunks)} generating, "
                  f"{self.chunks_to_build_mesh.qsize()} awaiting mesh")

        # Always show stats periodically
        if completed > 0 or mesh_builds > 0 or cleanups > 0:
            if completed > 0:
                print(f"Processed {completed} generated chunks")
            if mesh_builds > 0:
                print(f"Built {mesh_builds} chunk meshes")
            if cleanups > 0:
                print(f"Cleaned {cleanups} chunks")
    
    def get_visible_chunks(self, camera_position):
        """Get chunks that should be rendered with basic frustum culling"""
        player_chunk_x, player_chunk_z = self.get_chunk_coords(camera_position[0], camera_position[2])
        
        visible_chunks = []
        for (chunk_x, chunk_z), chunk in self.chunks.items():
            # Distance check
            distance = max(abs(chunk_x - player_chunk_x), abs(chunk_z - player_chunk_z))
            if distance <= RENDER_DISTANCE:
                # Only add chunks that have their mesh built
                if not chunk.needs_update and chunk.vertex_count > 0:
                    visible_chunks.append(chunk)

        # FIX: Sort by distance so closer chunks render first (better for depth testing)
        visible_chunks.sort(key=lambda c:
            max(abs(c.x - player_chunk_x), abs(c.z - player_chunk_z))
        )
        
        return visible_chunks
    
    def cleanup(self):
        """Clean up all chunks and stop generation threads"""
        # Stop generation threads
        self.stop_generation = True
        
        # Wait for threads to finish
        for thread in self.generation_threads:
            thread.join(timeout=1.0)
        
        # Clean up all chunks
        for chunk in self.chunks.values():
            chunk.cleanup()
        self.chunks.clear()

        # Clear deferred operation queues
        for chunk in self.chunks_to_cleanup:
            chunk.cleanup()
        self.chunks_to_cleanup.clear()

        print(f"Cleanup stats: Generated {self.generation_stats['total_generated']}, "
              f"Cleaned {self.generation_stats['total_cleaned']}, "
              f"Meshes built {self.generation_stats['meshes_built']}")