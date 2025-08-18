"""
OpenGL shader management.
"""
import pygame
from OpenGL.GL import *


class Shader:
    def __init__(self, vertex_source, fragment_source):
        self.program = glCreateProgram()
        
        # Create and compile vertex shader
        vertex_shader = glCreateShader(GL_VERTEX_SHADER)
        glShaderSource(vertex_shader, vertex_source)
        glCompileShader(vertex_shader)
        
        # Check for vertex shader compilation errors
        if not glGetShaderiv(vertex_shader, GL_COMPILE_STATUS):
            error = glGetShaderInfoLog(vertex_shader).decode()
            raise RuntimeError(f"Vertex shader compilation failed: {error}")
        
        # Create and compile fragment shader
        fragment_shader = glCreateShader(GL_FRAGMENT_SHADER)
        glShaderSource(fragment_shader, fragment_source)
        glCompileShader(fragment_shader)
        
        # Check for fragment shader compilation errors
        if not glGetShaderiv(fragment_shader, GL_COMPILE_STATUS):
            error = glGetShaderInfoLog(fragment_shader).decode()
            raise RuntimeError(f"Fragment shader compilation failed: {error}")
        
        # Attach shaders to program
        glAttachShader(self.program, vertex_shader)
        glAttachShader(self.program, fragment_shader)
        
        # Link program
        glLinkProgram(self.program)
        
        # Check for linking errors
        if not glGetProgramiv(self.program, GL_LINK_STATUS):
            error = glGetProgramInfoLog(self.program).decode()
            raise RuntimeError(f"Shader program linking failed: {error}")
        
        # Clean up shaders (they're now linked into the program)
        glDeleteShader(vertex_shader)
        glDeleteShader(fragment_shader)
        
        # Store uniform locations
        self.uniforms = {}
    
    def use(self):
        glUseProgram(self.program)
    
    def get_uniform_location(self, name):
        if name not in self.uniforms:
            self.uniforms[name] = glGetUniformLocation(self.program, name)
        return self.uniforms[name]
    
    def set_mat4(self, name, matrix):
        location = glGetUniformLocation(self.program, name)
        # Set GL_TRUE to transpose the matrix from NumPy's row-major to OpenGL's column-major format
        glUniformMatrix4fv(location, 1, GL_TRUE, matrix)
    
    def set_vec3(self, name, vector):
        location = glGetUniformLocation(self.program, name)
        glUniform3f(location, vector[0], vector[1], vector[2])
    
    def set_float(self, name, value):
        location = glGetUniformLocation(self.program, name)
        glUniform1f(location, value)
    
    def cleanup(self):
        glDeleteProgram(self.program)
