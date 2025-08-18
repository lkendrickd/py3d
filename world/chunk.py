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
        self.mesh_data = None
        self.needs_update = True

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
    
    def generate_mesh_data(self):
        """
        Generate vertex and index data for the chunk mesh using greedy meshing.
        This method is thread-safe as it does not involve any OpenGL calls.
        """
        from config.settings import BLOCK_COLORS

        vertices = []
        indices = []
        vertex_map = {}
        dims = [CHUNK_SIZE, 64, CHUNK_SIZE]

        for axis in range(3):
            for direction in [1, -1]:
                u_axis, v_axis = (axis + 1) % 3, (axis + 2) % 3
                normal = [0, 0, 0]
                normal[axis] = direction
                mask_dims = [dims[u_axis], dims[v_axis]]
                mask = np.zeros(mask_dims, dtype=np.int32)

                for slice_idx in range(dims[axis]):
                    mask.fill(0)
                    for u in range(mask_dims[0]):
                        for v in range(mask_dims[1]):
                            pos = [0, 0, 0]
                            pos[axis], pos[u_axis], pos[v_axis] = slice_idx, u, v
                            block_type = self.blocks[pos[0], pos[1], pos[2]]
                            if block_type == Block.AIR: continue

                            adj_pos = pos.copy(); adj_pos[axis] += direction
                            is_face_visible = not (0 <= adj_pos[0] < dims[0] and 0 <= adj_pos[1] < dims[1] and 0 <= adj_pos[2] < dims[2]) or \
                                              self.blocks[adj_pos[0], adj_pos[1], adj_pos[2]] == Block.AIR
                            if is_face_visible: mask[u, v] = block_type
                    
                    for u_start in range(mask_dims[0]):
                        for v_start in range(mask_dims[1]):
                            block_type = mask[u_start, v_start]
                            if not block_type: continue

                            width = 1
                            while u_start + width < mask_dims[0] and mask[u_start + width, v_start] == block_type:
                                width += 1

                            height = 1
                            done = False
                            while v_start + height < mask_dims[1]:
                                for i in range(width):
                                    if mask[u_start + i, v_start + height] != block_type:
                                        done = True; break
                                if done: break
                                height += 1

                            p = [0,0,0]; p[axis] = slice_idx + (1 if direction == 1 else 0)
                            p[u_axis], p[v_axis] = u_start, v_start; v1 = p.copy()
                            p[u_axis] += width; v2 = p.copy()
                            p[v_axis] += height; v3 = p.copy()
                            p[u_axis] -= width; v4 = p.copy()

                            quad_verts = [v1, v2, v3, v4]
                            if direction == -1: quad_verts = [quad_verts[0], quad_verts[3], quad_verts[2], quad_verts[1]]

                            color = BLOCK_COLORS[block_type]
                            if normal[1] == -1: color *= 0.5
                            elif normal[2] != 0: color *= 0.8
                            elif normal[0] != 0: color *= 0.9

                            quad_indices = []
                            for vert_local in quad_verts:
                                vert_world = (self.x * CHUNK_SIZE + vert_local[0], vert_local[1], self.z * CHUNK_SIZE + vert_local[2])
                                key = (vert_world, tuple(normal))
                                if key not in vertex_map:
                                    vertex_map[key] = len(vertices)
                                    vertices.extend([*vert_world, *normal, *color])
                                quad_indices.append(vertex_map[key])

                            indices.extend([quad_indices[0], quad_indices[1], quad_indices[2], quad_indices[0], quad_indices[2], quad_indices[3]])
                            mask[u_start:u_start+width, v_start:v_start+height] = 0
        
        self.needs_update = False
        if not vertices:
            return None
        
        return (np.array(vertices, dtype=np.float32), np.array(indices, dtype=np.uint32))

    
    def cleanup(self):
        """Chunks no longer hold GPU resources, so cleanup is simplified."""
        self.mesh_data = None