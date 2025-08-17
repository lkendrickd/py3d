"""
Chunk system for world generation and rendering - FIXED VERSION.
"""
import numpy as np
from OpenGL.GL import *
from world.blocks import Block
from config.settings import CHUNK_SIZE


class Chunk:
    def __init__(self, x, z):
        self.x = x
        self.z = z
        self.blocks = np.zeros((CHUNK_SIZE, 64, CHUNK_SIZE), dtype=np.uint8)
        self.vao = None
        self.vbo = None
        self.vertex_count = 0
        self.needs_update = True
        
        # FIX: Add flag to track if mesh build is queued
        self.mesh_build_queued = False
        
        self.generate_terrain()
    
    def generate_terrain(self):
        """Generate chunk terrain with complex height map, water, and trees"""
        import math
        import random
        
        for x in range(CHUNK_SIZE):
            for z in range(CHUNK_SIZE):
                world_x = self.x * CHUNK_SIZE + x
                world_z = self.z * CHUNK_SIZE + z
                
                # Complex height generation using sine waves
                height = int(20 + 8 * math.sin(world_x * 0.1) * math.cos(world_z * 0.1) + 
                           4 * math.sin(world_x * 0.2) + 3 * math.cos(world_z * 0.15))
                height = np.clip(height, 10, 64 - 10)
                
                # Fill blocks
                for y in range(height):
                    if y < height - 4:
                        self.blocks[x, y, z] = Block.STONE
                    elif y < height - 1:
                        self.blocks[x, y, z] = Block.DIRT
                    else:
                        self.blocks[x, y, z] = Block.GRASS
                
                # Add water at sea level
                if height < 18:
                    for y in range(height, 18):
                        self.blocks[x, y, z] = Block.WATER
                
                # Occasionally add trees
                if height > 18 and self.blocks[x, height-1, z] == Block.GRASS and random.random() < 0.01:
                    # Simple tree
                    tree_height = random.randint(4, 7)
                    for h in range(tree_height):
                        if height + h < 64:
                            self.blocks[x, height + h, z] = Block.WOOD
                    
                    # Add leaves
                    leaf_start = height + tree_height - 2
                    for lx in range(max(0, x-2), min(CHUNK_SIZE, x+3)):
                        for lz in range(max(0, z-2), min(CHUNK_SIZE, z+3)):
                            for ly in range(leaf_start, min(64, leaf_start + 3)):
                                if self.blocks[lx, ly, lz] == Block.AIR:
                                    self.blocks[lx, ly, lz] = Block.LEAVES
    
    def get_block(self, x, y, z):
        """Get block at local coordinates"""
        if 0 <= x < CHUNK_SIZE and 0 <= y < 64 and 0 <= z < CHUNK_SIZE:
            return self.blocks[x, y, z]
        return Block.AIR
    
    def set_block(self, x, y, z, block_type):
        """Set block at local coordinates"""
        if 0 <= x < CHUNK_SIZE and 0 <= y < 64 and 0 <= z < CHUNK_SIZE:
            self.blocks[x, y, z] = block_type
            self.needs_update = True  # FIX: Set flag instead of dirty
    
    def is_face_visible(self, x, y, z, face_dir):
        """Check if a face should be rendered (not occluded by adjacent block)"""
        dx, dy, dz = face_dir
        adj_x, adj_y, adj_z = x + dx, y + dy, z + dz
        
        # Check adjacent block
        adjacent_block = self.get_block(adj_x, adj_y, adj_z)
        return adjacent_block == Block.AIR
    
    def add_face(self, vertices, x, y, z, direction, color):
        """Add a face (2 triangles) to the vertex list"""
        if direction == 'top':
            normal = [0, 1, 0]
            # Triangle 1
            vertices.extend([x, y+1, z, *normal, *color])
            vertices.extend([x+1, y+1, z+1, *normal, *color])
            vertices.extend([x+1, y+1, z, *normal, *color])
            # Triangle 2
            vertices.extend([x, y+1, z, *normal, *color])
            vertices.extend([x, y+1, z+1, *normal, *color])
            vertices.extend([x+1, y+1, z+1, *normal, *color])
        elif direction == 'bottom':
            normal = [0, -1, 0]
            # Triangle 1
            vertices.extend([x, y, z, *normal, *color])
            vertices.extend([x+1, y, z, *normal, *color])
            vertices.extend([x+1, y, z+1, *normal, *color])
            # Triangle 2
            vertices.extend([x, y, z, *normal, *color])
            vertices.extend([x+1, y, z+1, *normal, *color])
            vertices.extend([x, y, z+1, *normal, *color])
        elif direction == 'front':
            normal = [0, 0, 1]
            # Triangle 1
            vertices.extend([x, y, z+1, *normal, *color])
            vertices.extend([x+1, y+1, z+1, *normal, *color])
            vertices.extend([x, y+1, z+1, *normal, *color])
            # Triangle 2
            vertices.extend([x, y, z+1, *normal, *color])
            vertices.extend([x+1, y, z+1, *normal, *color])
            vertices.extend([x+1, y+1, z+1, *normal, *color])
        elif direction == 'back':
            normal = [0, 0, -1]
            # Triangle 1
            vertices.extend([x, y, z, *normal, *color])
            vertices.extend([x, y+1, z, *normal, *color])
            vertices.extend([x+1, y+1, z, *normal, *color])
            # Triangle 2
            vertices.extend([x, y, z, *normal, *color])
            vertices.extend([x+1, y+1, z, *normal, *color])
            vertices.extend([x+1, y, z, *normal, *color])
        elif direction == 'right':
            normal = [1, 0, 0]
            # Triangle 1
            vertices.extend([x+1, y, z, *normal, *color])
            vertices.extend([x+1, y+1, z, *normal, *color])
            vertices.extend([x+1, y+1, z+1, *normal, *color])
            # Triangle 2
            vertices.extend([x+1, y, z, *normal, *color])
            vertices.extend([x+1, y+1, z+1, *normal, *color])
            vertices.extend([x+1, y, z+1, *normal, *color])
        else:  # left
            normal = [-1, 0, 0]
            # Triangle 1
            vertices.extend([x, y, z, *normal, *color])
            vertices.extend([x, y+1, z+1, *normal, *color])
            vertices.extend([x, y+1, z, *normal, *color])
            # Triangle 2
            vertices.extend([x, y, z, *normal, *color])
            vertices.extend([x, y, z+1, *normal, *color])
            vertices.extend([x, y+1, z+1, *normal, *color])
    
    def build_mesh(self):
        """Build the mesh for this chunk"""
        from config.settings import BLOCK_COLORS
        
        # FIX: Early return if OpenGL context is not ready
        try:
            # Test if we can generate arrays
            if self.vao is None:
                test_vao = glGenVertexArrays(1)
                if test_vao == 0:
                    print(f"Warning: Cannot create VAO for chunk ({self.x}, {self.z}) - OpenGL not ready")
                    return
                # Delete test VAO
                glDeleteVertexArrays(1, [test_vao])
        except Exception as e:
            print(f"Warning: OpenGL not ready for chunk ({self.x}, {self.z}): {e}")
            return
        
        vertices = []
        
        for x in range(CHUNK_SIZE):
            for y in range(64):
                for z in range(CHUNK_SIZE):
                    if self.blocks[x, y, z] == Block.AIR:
                        continue
                    
                    block_type = self.blocks[x, y, z]
                    color = BLOCK_COLORS[block_type]
                    world_x = self.x * CHUNK_SIZE + x
                    world_z = self.z * CHUNK_SIZE + z
                    
                    # Check each face for visibility and add vertices
                    # Top face (y+1)
                    if y == 64 - 1 or self.blocks[x, y + 1, z] == Block.AIR:
                        self.add_face(vertices, world_x, y, world_z, 'top', color)
                    
                    # Bottom face (y-1)
                    if y == 0 or self.blocks[x, y - 1, z] == Block.AIR:
                        self.add_face(vertices, world_x, y, world_z, 'bottom', color * 0.5)
                    
                    # Front face (z+1)
                    if z == CHUNK_SIZE - 1 or self.blocks[x, y, z + 1] == Block.AIR:
                        self.add_face(vertices, world_x, y, world_z, 'front', color * 0.8)
                    
                    # Back face (z-1)
                    if z == 0 or self.blocks[x, y, z - 1] == Block.AIR:
                        self.add_face(vertices, world_x, y, world_z, 'back', color * 0.8)
                    
                    # Right face (x+1)
                    if x == CHUNK_SIZE - 1 or self.blocks[x + 1, y, z] == Block.AIR:
                        self.add_face(vertices, world_x, y, world_z, 'right', color * 0.9)
                    
                    # Left face (x-1)
                    if x == 0 or self.blocks[x - 1, y, z] == Block.AIR:
                        self.add_face(vertices, world_x, y, world_z, 'left', color * 0.9)
        
        if not vertices:
            self.vertex_count = 0
            self.needs_update = False  # FIX: Mark as updated even if empty
            return
        
        # Convert to numpy array
        vertex_data = np.array(vertices, dtype=np.float32)
        self.vertex_count = len(vertices) // 9  # Number of vertices (9 floats per vertex)
        
        # Create VAO and VBO
        if self.vao is None:
            self.vao = glGenVertexArrays(1)
            self.vbo = glGenBuffers(1)
        
        # Bind VAO
        glBindVertexArray(self.vao)
        
        # Bind and upload vertex data
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, vertex_data.nbytes, vertex_data, GL_STATIC_DRAW)
        
        # Position attribute (location 0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 9 * 4, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        
        # Normal attribute (location 1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 9 * 4, ctypes.c_void_p(3 * 4))
        glEnableVertexAttribArray(1)
        
        # Color attribute (location 2)
        glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, 9 * 4, ctypes.c_void_p(6 * 4))
        glEnableVertexAttribArray(2)
        
        # Unbind
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindVertexArray(0)
        
        self.needs_update = False
        self.mesh_build_queued = False  # FIX: Clear queued flag
    
    def render(self):
        """FIX: Render this chunk without building mesh synchronously"""
        # FIX: Don't build mesh during render - this should be done by WorldManager
        # if self.needs_update:
        #     self.build_mesh()  # REMOVED - This causes frame drops!
        
        # Only render if we have a built mesh
        if self.vertex_count > 0 and self.vao is not None:
            glBindVertexArray(self.vao)
            glDrawArrays(GL_TRIANGLES, 0, self.vertex_count)  # vertex_count is already the number of vertices
            glBindVertexArray(0)
        # Debug: print if chunk needs update but hasn't been built
        elif self.needs_update and not hasattr(self, '_warned_needs_update'):
            print(f"Info: Chunk ({self.x}, {self.z}) needs mesh build")
            self._warned_needs_update = True
    
    def cleanup(self):
        """Clean up OpenGL resources"""
        if self.vao is not None:
            try:
                glDeleteVertexArrays(1, [self.vao])
                glDeleteBuffers(1, [self.vbo])
            except Exception as e:
                print(f"Warning: Error cleaning up chunk ({self.x}, {self.z}): {e}")
            finally:
                self.vao = None
                self.vbo = None
                self.vertex_count = 0