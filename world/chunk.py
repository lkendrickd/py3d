"""
Chunk system for world generation and rendering - FIXED VERSION.
"""
import numpy as np
from world.blocks import Block
from config.settings import CHUNK_SIZE


class Chunk:
    def __init__(self, x, z):
        self.x = x
        self.z = z
        self.blocks = np.zeros((CHUNK_SIZE, 64, CHUNK_SIZE), dtype=np.uint8)

        self.needs_update = True
        self.mesh_build_queued = False
        self.mesh_handle = None # Will store a handle to the mesh in the batch

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
            self.needs_update = True
    
    def is_face_visible(self, x, y, z, face_dir):
        """Check if a face should be rendered (not occluded by adjacent block)"""
        dx, dy, dz = face_dir
        adj_x, adj_y, adj_z = x + dx, y + dy, z + dz
        
        adjacent_block = self.get_block(adj_x, adj_y, adj_z)
        return adjacent_block == Block.AIR
    
    def add_face(self, vertices, x, y, z, direction, color):
        """Add a face (2 triangles) to the vertex list"""
        if direction == 'top':
            normal = [0, 1, 0]
            vertices.extend([x, y+1, z, *normal, *color, x+1, y+1, z+1, *normal, *color, x+1, y+1, z, *normal, *color])
            vertices.extend([x, y+1, z, *normal, *color, x, y+1, z+1, *normal, *color, x+1, y+1, z+1, *normal, *color])
        elif direction == 'bottom':
            normal = [0, -1, 0]
            vertices.extend([x, y, z, *normal, *color, x+1, y, z, *normal, *color, x+1, y, z+1, *normal, *color])
            vertices.extend([x, y, z, *normal, *color, x+1, y, z+1, *normal, *color, x, y, z+1, *normal, *color])
        elif direction == 'front':
            normal = [0, 0, 1]
            vertices.extend([x, y, z+1, *normal, *color, x+1, y+1, z+1, *normal, *color, x, y+1, z+1, *normal, *color])
            vertices.extend([x, y, z+1, *normal, *color, x+1, y, z+1, *normal, *color, x+1, y+1, z+1, *normal, *color])
        elif direction == 'back':
            normal = [0, 0, -1]
            vertices.extend([x, y, z, *normal, *color, x, y+1, z, *normal, *color, x+1, y+1, z, *normal, *color])
            vertices.extend([x, y, z, *normal, *color, x+1, y+1, z, *normal, *color, x+1, y, z, *normal, *color])
        elif direction == 'right':
            normal = [1, 0, 0]
            vertices.extend([x+1, y, z, *normal, *color, x+1, y+1, z, *normal, *color, x+1, y+1, z+1, *normal, *color])
            vertices.extend([x+1, y, z, *normal, *color, x+1, y+1, z+1, *normal, *color, x+1, y, z+1, *normal, *color])
        else:  # left
            normal = [-1, 0, 0]
            vertices.extend([x, y, z, *normal, *color, x, y+1, z+1, *normal, *color, x, y+1, z, *normal, *color])
            vertices.extend([x, y, z, *normal, *color, x, y, z+1, *normal, *color, x, y+1, z+1, *normal, *color])

    def build_mesh(self):
        """Build the mesh for this chunk and return the vertex data"""
        from config.settings import BLOCK_COLORS

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
                    
                    if y == 64 - 1 or self.blocks[x, y + 1, z] == Block.AIR:
                        self.add_face(vertices, world_x, y, world_z, 'top', color)
                    if y == 0 or self.blocks[x, y - 1, z] == Block.AIR:
                        self.add_face(vertices, world_x, y, world_z, 'bottom', color * 0.5)
                    if z == CHUNK_SIZE - 1 or self.blocks[x, y, z + 1] == Block.AIR:
                        self.add_face(vertices, world_x, y, world_z, 'front', color * 0.8)
                    if z == 0 or self.blocks[x, y, z - 1] == Block.AIR:
                        self.add_face(vertices, world_x, y, world_z, 'back', color * 0.8)
                    if x == CHUNK_SIZE - 1 or self.blocks[x + 1, y, z] == Block.AIR:
                        self.add_face(vertices, world_x, y, world_z, 'right', color * 0.9)
                    if x == 0 or self.blocks[x - 1, y, z] == Block.AIR:
                        self.add_face(vertices, world_x, y, world_z, 'left', color * 0.9)
        
        self.needs_update = False
        self.mesh_build_queued = False
        
        if not vertices:
            return None

        return np.array(vertices, dtype=np.float32)

    def cleanup(self):
        """Chunk cleanup logic (if any)"""
        # Since the mesh is now in a shared batch, the chunk itself has no OpenGL resources to clean up.
        # If we were to implement mesh removal from the batch, this is where we would trigger it.
        pass