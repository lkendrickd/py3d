"""
World manager for dynamic chunk loading and unloading.
"""
import math
import threading
import queue
import time
from collections import defaultdict
from world.chunk import Chunk
from config.settings import CHUNK_SIZE, RENDER_DISTANCE, PRELOAD_DISTANCE, UNLOAD_DISTANCE


class WorldManager:
    def __init__(self):
        self.chunks = {}  # Dictionary to store loaded chunks (x, z) -> Chunk
        self.last_player_chunk = (None, None)  # Last chunk position of player
        self.max_chunks = UNLOAD_DISTANCE * UNLOAD_DISTANCE * 4  # Memory limit based on unload distance
        
        # Threading for chunk generation
        self.chunk_queue = queue.Queue()  # Queue for chunks to generate
        self.completed_chunks = queue.Queue()  # Queue for completed chunks
        self.generating_chunks = set()  # Set of chunk coords currently being generated
        self.generation_threads = []
        self.stop_generation = False
        
        # GPU resource cleanup
        self.cleanup_queue = queue.Queue()

        # Use multiple threads for better performance
        self.num_threads = min(6, max(3, threading.active_count()))  # 3-6 threads based on system
        
        # Priority system for chunk generation
        self.priority_queue = queue.PriorityQueue()  # (priority, chunk_coords)
        self.use_priority_queue = True
        
        # Performance tracking
        self.chunks_generated_this_frame = 0
        self.max_chunks_per_frame = 1  # Base processing rate
        self.frame_budget_ms = 2.0  # Maximum 2ms per frame for chunk processing
        self.last_process_time = 0
        self.aggressive_preload = True  # Enable aggressive pre-loading
        
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
                        chunk_coords = self.chunk_queue.get(timeout=0.05)
                else:
                    chunk_coords = self.chunk_queue.get(timeout=0.1)
                
                chunk_x, chunk_z = chunk_coords
                
                # Generate the chunk and its vertex data
                start_time = time.time()
                chunk = Chunk(chunk_x, chunk_z)
                vertex_data = chunk.generate_vertex_data()
                generation_time = time.time() - start_time

                # Put completed chunk and data in the completed queue
                self.completed_chunks.put((chunk_coords, chunk, vertex_data, generation_time))
                
                # Remove from generating set
                self.generating_chunks.discard(chunk_coords)
                
                # Mark task as done (simplified approach)
                try:
                    self.chunk_queue.task_done()
                except:
                    try:
                        self.priority_queue.task_done()
                    except:
                        pass
                
            except queue.Empty:
                continue  # Check stop condition and continue
            except Exception as e:
                print(f"Error generating chunk {chunk_coords}: {e}")
                if chunk_coords is not None:
                    self.generating_chunks.discard(chunk_coords)
                    # Try to mark task done for both queues
                    try:
                        self.chunk_queue.task_done()
                    except:
                        pass
                    try:
                        self.priority_queue.task_done()
                    except:
                        pass
    
    def process_completed_chunks(self):
        """Process completed chunks from the generation threads with time budget"""
        import time
        start_time = time.time() * 1000  # Convert to milliseconds
        
        chunks_added = 0
        total_generation_time = 0
        
        # Process chunks but respect time budget
        while chunks_added < self.max_chunks_per_frame:
            # Check if we've exceeded our time budget
            current_time = time.time() * 1000
            if current_time - start_time > self.frame_budget_ms:
                break
            
            try:
                # Get the generated data from the queue
                chunk_coords, chunk, vertex_data, generation_time = self.completed_chunks.get_nowait()

                # Create GPU buffers on the main thread
                if vertex_data is not None:
                    chunk.create_gpu_buffers(vertex_data)

                # Add the finalized chunk to the world
                self.chunks[chunk_coords] = chunk
                chunks_added += 1
                total_generation_time += generation_time
                
                # Update performance tracking
                self.chunks_generated_this_frame += 1
                
            except queue.Empty:
                break
        
        # Track processing time for next frame
        self.last_process_time = time.time() * 1000 - start_time
        
        # Reduce logging frequency significantly
        if chunks_added > 0 and total_generation_time > 0:
            avg_time = total_generation_time / chunks_added
            # Only log occasionally and when we have significant data
            if chunks_added > 0 and len(self.chunks) % 50 == 0:  # Every 50 chunks
                print(f"Processed {chunks_added} chunks (avg: {avg_time:.3f}s, budget: {self.last_process_time:.1f}ms)")
        
        return chunks_added
    
    def request_chunk_generation(self, chunk_x, chunk_z, priority=None):
        """Request a chunk to be generated asynchronously with optional priority"""
        chunk_coords = (chunk_x, chunk_z)
        
        # Don't generate if already exists or is being generated
        if chunk_coords in self.chunks or chunk_coords in self.generating_chunks:
            return False
        
        # Add to generation queue
        self.generating_chunks.add(chunk_coords)
        
        # Use priority queue if priority is specified and closer chunks get higher priority
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
        """Load initial chunks around camera position with aggressive pre-generation"""
        player_chunk_x, player_chunk_z = self.get_chunk_coords(camera_position[0], camera_position[2])
        
        print(f"Pre-generating world around chunk ({player_chunk_x}, {player_chunk_z})...")
        
        # Phase 1: Load immediate chunks synchronously (larger area for smoother experience)
        immediate_radius = 2  # Increased from 1 to 2 for more immediate coverage
        chunks_loaded = 0
        
        print("Phase 1: Loading immediate chunks synchronously...")
        for dx in range(-immediate_radius, immediate_radius + 1):
            for dz in range(-immediate_radius, immediate_radius + 1):
                chunk_x = player_chunk_x + dx
                chunk_z = player_chunk_z + dz
                key = (chunk_x, chunk_z)
                
                if key not in self.chunks:
                    # Load these initial chunks synchronously for immediate gameplay
                    self.chunks[key] = Chunk(chunk_x, chunk_z)
                    chunks_loaded += 1
        
        print(f"Phase 1 complete: {chunks_loaded} immediate chunks loaded")
        
        # Phase 2: Queue up a substantial area for background generation
        print("Phase 2: Queuing chunks for background generation...")
        preload_radius = min(PRELOAD_DISTANCE // 3, 12)  # Increased from 8 to 12 chunks radius
        chunks_queued = 0
        
        # Generate chunks in rings, prioritizing closer ones
        for radius in range(immediate_radius + 1, preload_radius + 1):
            ring_priority = radius  # Lower number = higher priority
            
            for dx in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    # Only generate chunks on the edge of this radius
                    if max(abs(dx), abs(dz)) == radius:
                        chunk_x = player_chunk_x + dx
                        chunk_z = player_chunk_z + dz
                        
                        # Request generation with priority (closer = higher priority)
                        if self.request_chunk_generation(chunk_x, chunk_z, ring_priority):
                            chunks_queued += 1
        
        print(f"Phase 2 complete: {chunks_queued} chunks queued for background generation")
        print(f"Total initial setup: {chunks_loaded} immediate + {chunks_queued} queued = {chunks_loaded + chunks_queued} chunks")
        
        return chunks_loaded
    
    def unload_distant_chunks(self, player_chunk_x, player_chunk_z):
        """Unload chunks that are too far from the player by queueing their resources for cleanup."""
        chunks_to_remove = []
        
        for (chunk_x, chunk_z), chunk in self.chunks.items():
            distance = max(abs(chunk_x - player_chunk_x), abs(chunk_z - player_chunk_z))
            if distance > UNLOAD_DISTANCE:
                chunks_to_remove.append((chunk_x, chunk_z))
        
        # Queue GPU resources for cleanup and remove chunk from world
        for key in chunks_to_remove:
            chunk = self.chunks.pop(key, None)
            if chunk:
                self.cleanup_queue.put(chunk.get_gpu_resources())
                chunk.cleanup()  # Clear local references
        
        if chunks_to_remove:
            print(f"Queued {len(chunks_to_remove)} chunks for cleanup beyond {UNLOAD_DISTANCE} chunk distance")

    def process_cleanup_queue(self):
        """Process a few GPU resources from the cleanup queue each frame."""
        from OpenGL.GL import glDeleteVertexArrays, glDeleteBuffers
        max_deletions_per_frame = 10  # Limit deletions per frame to avoid stutter
        for _ in range(max_deletions_per_frame):
            if not self.cleanup_queue.empty():
                try:
                    vao, vbo = self.cleanup_queue.get_nowait()
                    if vao:
                        glDeleteVertexArrays(1, [vao])
                    if vbo:
                        glDeleteBuffers(1, [vbo])
                except queue.Empty:
                    break
            else:
                break

    def update(self, camera_position):
        """Update world based on camera position with performance optimization"""
        # Reset frame counter
        self.chunks_generated_this_frame = 0
        
        # Process queues
        completed = self.process_completed_chunks()
        self.process_cleanup_queue()
        
        # Get player's current chunk
        player_chunk_x, player_chunk_z = self.get_chunk_coords(camera_position[0], camera_position[2])
        
        # Check if player moved to a different chunk
        if (player_chunk_x, player_chunk_z) != self.last_player_chunk:
            print(f"Player moved to chunk ({player_chunk_x}, {player_chunk_z})")
            self.last_player_chunk = (player_chunk_x, player_chunk_z)
            
            # Request chunks around the player to be generated asynchronously with priority
            chunks_requested = 0
            max_requests_per_update = 12  # Increased from 8 to 12 for better coverage
            
            # Generate in expanding rings with priority (closer = higher priority)
            for radius in range(1, RENDER_DISTANCE + 5):  # Slightly beyond render distance
                if chunks_requested >= max_requests_per_update:
                    break
                
                ring_priority = radius  # Lower number = higher priority
                    
                for dx in range(-radius, radius + 1):
                    for dz in range(-radius, radius + 1):
                        if chunks_requested >= max_requests_per_update:
                            break
                            
                        # Only load chunks on the border of this radius
                        if max(abs(dx), abs(dz)) == radius:
                            chunk_x = player_chunk_x + dx
                            chunk_z = player_chunk_z + dz
                            
                            # Use priority for chunks within render distance
                            priority = ring_priority if radius <= RENDER_DISTANCE else None
                            if self.request_chunk_generation(chunk_x, chunk_z, priority):
                                chunks_requested += 1
            
            if chunks_requested > 0:
                print(f"Requested {chunks_requested} new chunks for generation (with priority)")
            
            # Unload distant chunks to save memory (essential for performance!)
            self.unload_distant_chunks(player_chunk_x, player_chunk_z)
            
            print(f"Total chunks loaded: {len(self.chunks)}")
        
        # Always process completed chunks, even if player didn't move
        elif completed > 0:
            print(f"Processed {completed} background-generated chunks")
            
            # Unload distant chunks to save memory
            self.unload_distant_chunks(player_chunk_x, player_chunk_z)
            
            print(f"Total chunks loaded: {len(self.chunks)}")
    
    def get_visible_chunks(self, camera_position):
        """Get chunks that should be rendered"""
        player_chunk_x, player_chunk_z = self.get_chunk_coords(camera_position[0], camera_position[2])
        
        visible_chunks = []
        for (chunk_x, chunk_z), chunk in self.chunks.items():
            # Simple distance check - could be improved with frustum culling
            distance = max(abs(chunk_x - player_chunk_x), abs(chunk_z - player_chunk_z))
            if distance <= RENDER_DISTANCE:
                visible_chunks.append(chunk)
        
        return visible_chunks
    
    def cleanup(self):
        """Clean up all chunks and stop generation threads"""
        # Stop generation threads
        self.stop_generation = True
        
        # Wait for threads to finish
        for thread in self.generation_threads:
            thread.join(timeout=1.0)
        
        # Queue all remaining chunks for cleanup
        for chunk in self.chunks.values():
            self.cleanup_queue.put(chunk.get_gpu_resources())
            chunk.cleanup()
        self.chunks.clear()

        # Process the entire cleanup queue
        print("Processing final cleanup...")
        while not self.cleanup_queue.empty():
            try:
                vao, vbo = self.cleanup_queue.get_nowait()
                if vao:
                    from OpenGL.GL import glDeleteVertexArrays
                    glDeleteVertexArrays(1, [vao])
                if vbo:
                    from OpenGL.GL import glDeleteBuffers
                    glDeleteBuffers(1, [vbo])
            except queue.Empty:
                break
        print("Cleanup complete.")
