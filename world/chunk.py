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
    
    def _world_get_block(self, world_manager, x, y, z):
        """Get a block from the world, crossing chunk boundaries if necessary."""
        if 0 <= x < CHUNK_SIZE and 0 <= y < 64 and 0 <= z < CHUNK_SIZE:
            return self.blocks[x, y, z]

        # It's in another chunk. Calculate world coordinates.
        world_x = self.x * CHUNK_SIZE + x
        world_y = y
        world_z = self.z * CHUNK_SIZE + z

        # Find the other chunk's coordinates
        other_chunk_x = int(math.floor(world_x / CHUNK_SIZE))
        other_chunk_z = int(math.floor(world_z / CHUNK_SIZE))

        # Get the other chunk from the world manager
        other_chunk = world_manager.get_chunk(other_chunk_x, other_chunk_z)

        if other_chunk is None:
            return Block.AIR # If neighbor isn't loaded, assume it's air

        # Get local coords within the other chunk
        local_x = world_x % CHUNK_SIZE
        local_z = world_z % CHUNK_SIZE

        return other_chunk.blocks[int(local_x), int(world_y), int(local_z)]

    def _generate_face_mask(self, mask, axis, slice_idx, direction, world_manager):
        """
        Generate a 2D mask for a slice of the chunk.
        The mask contains the block type for each visible face on that slice.
        """
        dims = (CHUNK_SIZE, 64, CHUNK_SIZE)
        u_axis = (axis + 1) % 3
        v_axis = (axis + 2) % 3

        u_dim = dims[u_axis]
        v_dim = dims[v_axis]

        for u in range(u_dim):
            for v in range(v_dim):
                # Map 2D mask coords (u, v) and slice_idx back to 3D chunk coords (x, y, z)
                coords_here = [0, 0, 0]
                coords_here[axis] = slice_idx
                coords_here[u_axis] = u
                coords_here[v_axis] = v

                # Determine the coordinates of the adjacent block
                coords_there = list(coords_here)
                coords_there[axis] += direction

                block_here = self._world_get_block(world_manager, *coords_here)
                block_there = self._world_get_block(world_manager, *coords_there)

                # A face is visible if one block is solid and the other is transparent.
                if block_here != Block.AIR and block_there == Block.AIR:
                    mask[u, v] = block_here
                else:
                    mask[u, v] = 0

    def _mesh_mask(self, mask, axis, slice_idx, direction):
        """
        Applies the greedy meshing algorithm to a 2D mask.
        Returns a list of quads (rectangles) that cover the mask.
        """
        quads = []
        height, width = mask.shape

        for u in range(height):
            for v in range(width):
                # If this face has already been processed or is empty, skip it
                if mask[u, v] == 0:
                    continue

                current_block_type = mask[u, v]

                # Find the width of the quad
                quad_width = 1
                while v + quad_width < width and mask[u, v + quad_width] == current_block_type:
                    quad_width += 1

                # Find the height of the quad
                quad_height = 1
                can_expand_height = True
                while u + quad_height < height and can_expand_height:
                    # Check if the entire row below is of the same block type
                    for i in range(quad_width):
                        if mask[u + quad_height, v + i] != current_block_type:
                            can_expand_height = False
                            break

                    if can_expand_height:
                        quad_height += 1

                # Add the quad to our list
                quad = {
                    "pos": (u, v),
                    "size": (quad_height, quad_width),
                    "block_type": current_block_type,
                    "axis": axis,
                    "slice_idx": slice_idx,
                    "direction": direction
                }
                quads.append(quad)

                # Zero out the mask for the area covered by this quad
                mask[u:u + quad_height, v:v + quad_width] = 0
        
        return quads

    def _build_vertex_buffer_from_quads(self, quads):
        """Build the final vertex buffer from a list of optimized quads."""
        from config.settings import BLOCK_COLORS
        import ctypes

        if not quads:
            self.vertex_count = 0
            if self.vao is not None:
                glDeleteVertexArrays(1, [self.vao])
                glDeleteBuffers(1, [self.vbo])
                self.vao, self.vbo = None, None
            return

        vertices = []
        chunk_offset = np.array([self.x * CHUNK_SIZE, 0, self.z * CHUNK_SIZE], dtype=np.float32)

        color_modifiers = {
            (0, 1): 0.9, (0, -1): 0.9,  # right/left
            (1, 1): 1.0, (1, -1): 0.5,  # top/bottom
            (2, 1): 0.8, (2, -1): 0.8,  # front/back
        }

        for quad in quads:
            u, v = quad["pos"]
            h, w = quad["size"]
            axis, slice_idx, direction = quad["axis"], quad["slice_idx"], quad["direction"]
            block_type = quad["block_type"]

            normal = [0, 0, 0]
            normal[axis] = direction

            base_color = BLOCK_COLORS[block_type]
            modifier = color_modifiers.get((axis, direction), 1.0)
            color = np.array(base_color, dtype=np.float32) * modifier

            u_axis, v_axis = (axis + 1) % 3, (axis + 2) % 3

            p0 = [0, 0, 0]
            p0[axis] = slice_idx + (1 if direction > 0 else 0)
            p0[u_axis], p0[v_axis] = u, v

            du, dv = [0, 0, 0], [0, 0, 0]
            du[u_axis], dv[v_axis] = h, w

            p0, du, dv = np.array(p0, dtype=np.float32), np.array(du, dtype=np.float32), np.array(dv, dtype=np.float32)
            p0 += chunk_offset

            c1, c2, c3, c4 = p0, p0 + dv, p0 + dv + du, p0 + du

            # Add two triangles with Counter-Clockwise (CCW) winding order
            vertices.extend([*c1, *normal, *color])
            vertices.extend([*c2, *normal, *color])
            vertices.extend([*c3, *normal, *color])

            vertices.extend([*c1, *normal, *color])
            vertices.extend([*c3, *normal, *color])
            vertices.extend([*c4, *normal, *color])

        vertex_data = np.array(vertices, dtype=np.float32)
        self.vertex_count = len(vertex_data) // 9
        
        if self.vao is None:
            self.vao = glGenVertexArrays(1)
            self.vbo = glGenBuffers(1)
        
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, vertex_data.nbytes, vertex_data, GL_STATIC_DRAW)
        
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 9 * 4, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 9 * 4, ctypes.c_void_p(3 * 4))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, 9 * 4, ctypes.c_void_p(6 * 4))
        glEnableVertexAttribArray(2)
        
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindVertexArray(0)

    def build_mesh(self, world_manager):
        """Build the mesh for this chunk using a greedy meshing algorithm."""
        
        # Ensure OpenGL context is available
        try:
            if self.vao is None:
                test_vao = glGenVertexArrays(1)
                if test_vao == 0:
                    print(f"Warning: Cannot create VAO for chunk ({self.x}, {self.z}) - OpenGL not ready")
                    return
                glDeleteVertexArrays(1, [test_vao])
        except Exception as e:
            print(f"Warning: OpenGL not ready for chunk ({self.x}, {self.z}): {e}")
            return

        quads = []

        # Dimensions of the chunk - assuming CHUNK_SIZE x 64 x CHUNK_SIZE
        dims = (CHUNK_SIZE, 64, CHUNK_SIZE)

        # Process each axis (X, Y, Z)
        for axis in range(3):
            # Process both directions (+ and -)
            for direction in [-1, 1]:

                # Define the two axes perpendicular to the current slicing axis
                u_axis = (axis + 1) % 3
                v_axis = (axis + 2) % 3

                # Create a 2D mask for this slice direction
                mask = np.zeros((dims[u_axis], dims[v_axis]), dtype=np.int32)

                # Scan along the current axis
                for slice_idx in range(dims[axis]):
                    # Generate the 2D mask for this slice
                    self._generate_face_mask(mask, axis, slice_idx, direction, world_manager)

                    # Greedy mesh the mask to generate quads
                    quads.extend(self._mesh_mask(mask, axis, slice_idx, direction))

        # Build the final vertex buffer from the list of quads
        self._build_vertex_buffer_from_quads(quads)

        self.needs_update = False
        self.mesh_build_queued = False
    
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