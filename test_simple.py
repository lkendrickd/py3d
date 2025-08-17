#!/usr/bin/env python3
"""
Simple test version of the voxel renderer that just initializes and exits
"""
import pygame as pg
from pygame.locals import DOUBLEBUF, OPENGL
from OpenGL.GL import *
import numpy as np

def simple_test():
    try:
        pg.init()
        
        # Set OpenGL attributes
        pg.display.gl_set_attribute(pg.GL_CONTEXT_MAJOR_VERSION, 3)
        pg.display.gl_set_attribute(pg.GL_CONTEXT_MINOR_VERSION, 3)
        pg.display.gl_set_attribute(pg.GL_CONTEXT_PROFILE_MASK, pg.GL_CONTEXT_PROFILE_COMPATIBILITY)
        
        screen = pg.display.set_mode((800, 600), DOUBLEBUF | OPENGL)
        pg.display.set_caption("Voxel Test")
        
        print("OpenGL Version:", glGetString(GL_VERSION).decode())
        
        # Test basic OpenGL operations
        glEnable(GL_DEPTH_TEST)
        glClearColor(0.5, 0.7, 0.9, 1.0)
        
        # Test VAO/VBO creation
        vao = glGenVertexArrays(1)
        vbo = glGenBuffers(1)
        print(f"Created VAO: {vao}, VBO: {vbo}")
        
        # Test vertex data
        vertices = np.array([
            0.0, 0.5, 0.0,
            -0.5, -0.5, 0.0,
            0.5, -0.5, 0.0
        ], dtype=np.float32)
        
        glBindVertexArray(vao)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 3 * 4, None)
        glEnableVertexAttribArray(0)
        
        print("OpenGL operations completed successfully!")
        
        # Clean up
        glBindVertexArray(0)
        pg.quit()
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = simple_test()
    print(f"Test {'PASSED' if success else 'FAILED'}")
