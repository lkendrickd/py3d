"""
Manages rendering the world by batching all visible chunk meshes into a
single draw call.
"""
import numpy as np
from OpenGL.GL import *
import ctypes

class WorldRenderer:
    def __init__(self):
        self.vao = glGenVertexArrays(1)
        self.vbo = glGenBuffers(1)
        self.ebo = glGenBuffers(1)

        glBindVertexArray(self.vao)

        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        # Position (3), Normal (3), Color (3)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 9 * 4, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 9 * 4, ctypes.c_void_p(3 * 4))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, 9 * 4, ctypes.c_void_p(6 * 4))
        glEnableVertexAttribArray(2)

        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)

        glBindVertexArray(0)

    def render_chunks(self, chunks):
        if not chunks:
            return

        # Combine mesh data from all visible chunks
        all_vertices = []
        all_indices = []
        index_offset = 0

        for chunk in chunks:
            if chunk.mesh_data:
                vertices, indices = chunk.mesh_data
                all_vertices.append(vertices)
                all_indices.append(indices + index_offset)
                index_offset += len(vertices) // 9 # 9 floats per vertex (pos, norm, color)

        if not all_vertices:
            return

        # Create single large buffers
        vertex_data = np.concatenate(all_vertices, dtype=np.float32)
        index_data = np.concatenate(all_indices, dtype=np.uint32)

        # Upload data to GPU
        glBindVertexArray(self.vao)

        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, vertex_data.nbytes, vertex_data, GL_DYNAMIC_DRAW)

        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, index_data.nbytes, index_data, GL_DYNAMIC_DRAW)

        # Single draw call for all chunks
        glDrawElements(GL_TRIANGLES, len(index_data), GL_UNSIGNED_INT, None)

        glBindVertexArray(0)

    def cleanup(self):
        glDeleteVertexArrays(1, [self.vao])
        glDeleteBuffers(2, [self.vbo, self.ebo])
