import numpy as np
from OpenGL.GL import *

class MeshBatch:
    def __init__(self, initial_size=1024 * 1024 * 10):  # 10 MB initial size
        self.vertex_size = 9 * 4  # 9 floats per vertex, 4 bytes per float

        self.vao = glGenVertexArrays(1)
        glBindVertexArray(self.vao)

        self.vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, initial_size, None, GL_DYNAMIC_DRAW)

        # Position attribute
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, self.vertex_size, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)

        # Normal attribute
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, self.vertex_size, ctypes.c_void_p(3 * 4))
        glEnableVertexAttribArray(1)

        # Color attribute
        glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, self.vertex_size, ctypes.c_void_p(6 * 4))
        glEnableVertexAttribArray(2)

        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindVertexArray(0)

        self.buffer_size = initial_size
        self.vertex_count = 0
        self.data = np.zeros(initial_size // 4, dtype=np.float32) # pre-allocated numpy array
        self.dirty = False

    def add_mesh(self, vertex_data):
        num_floats = len(vertex_data)
        num_vertices = num_floats // 9

        if (self.vertex_count + num_vertices) * self.vertex_size > self.buffer_size:
            # For simplicity, we'll just print a warning for now.
            # A more robust implementation would create a new batch or resize the buffer.
            print("Warning: Mesh batch is full. Cannot add new mesh.")
            return None

        offset = self.vertex_count * 9 # 9 floats per vertex
        self.data[offset : offset + num_floats] = vertex_data

        start_index = self.vertex_count
        self.vertex_count += num_vertices
        self.dirty = True

        # Return a handle that can be used to modify/remove the mesh later
        return (self, start_index, num_vertices)

    def update_buffer(self):
        if self.dirty:
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
            # Only update the part of the buffer that has changed.
            # For simplicity, we update the whole buffer for now.
            glBufferSubData(GL_ARRAY_BUFFER, 0, self.vertex_count * self.vertex_size, self.data)
            glBindBuffer(GL_ARRAY_BUFFER, 0)
            self.dirty = False

    def render(self):
        if self.vertex_count > 0:
            glBindVertexArray(self.vao)
            glDrawArrays(GL_TRIANGLES, 0, self.vertex_count)
            glBindVertexArray(0)

    def cleanup(self):
        if self.vbo:
            glDeleteBuffers(1, [self.vbo])
            self.vbo = None
        if self.vao:
            glDeleteVertexArrays(1, [self.vao])
            self.vao = None
