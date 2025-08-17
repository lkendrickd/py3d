#!/usr/bin/env python3
import pygame as pg
from pygame.locals import DOUBLEBUF, OPENGL
from OpenGL.GL import glGetString, GL_VERSION

def test_opengl():
    try:
        pg.init()
        screen = pg.display.set_mode((800, 600), DOUBLEBUF | OPENGL)
        pg.display.set_caption("OpenGL Test")
        
        version = glGetString(GL_VERSION)
        print(f"OpenGL Version: {version.decode()}")
        print("OpenGL context created successfully!")
        
        pg.quit()
        return True
    except Exception as e:
        print(f"Failed to create OpenGL context: {e}")
        return False

if __name__ == '__main__':
    test_opengl()
