"""
Main entry point for the 3D voxel world.
"""
import pygame
import numpy as np
import ctypes
import math
from OpenGL.GL import (
    GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, GL_CULL_FACE,
    GL_BACK, GL_CCW, GL_TRIANGLES, glEnable, glCullFace, glFrontFace,
    glClearColor, glClear, glDrawArrays, glBindVertexArray
)

from config.settings import *
from engine.shader import Shader
from engine.camera import Camera
from engine.math_utils import perspective
from world.chunk import Chunk


def main():
    # Initialize Pygame
    pygame.init()
    
    # Auto-detect native resolution
    info = pygame.display.Info()
    WINDOW_WIDTH = info.current_w
    WINDOW_HEIGHT = info.current_h
    print(f"Detected native resolution: {WINDOW_WIDTH}x{WINDOW_HEIGHT}")
    
    # Set OpenGL attributes before creating the display
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_COMPATIBILITY)
    pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)
    pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
    
    # Set up display
    pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.DOUBLEBUF | pygame.OPENGL)
    pygame.display.set_caption("GPU Voxel World")
    
    # Lock cursor to window
    pygame.mouse.set_visible(False)
    pygame.event.set_grab(True)
    
    # Enable depth testing and face culling
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_CULL_FACE)
    glCullFace(GL_BACK)
    glClearColor(0.53, 0.81, 0.92, 1.0)  # Sky blue
    
    # Create shader program
    shader = Shader(VERTEX_SHADER, FRAGMENT_SHADER)
    
    # Create camera
    camera = Camera()
    
    # Create chunks
    chunks = {}
    for cx in range(RENDER_DISTANCE):
        for cz in range(RENDER_DISTANCE):
            chunk = Chunk(cx, cz)
            chunks[(cx, cz)] = chunk
    
    print(f"World generated: {len(chunks)} chunks")
    
    # Matrices
    model = np.eye(4, dtype=np.float32)
    projection = perspective(math.radians(60), WINDOW_WIDTH / WINDOW_HEIGHT, 0.1, 1000.0)
    
    # Main loop
    clock = pygame.time.Clock()
    running = True
    
    while running:
        dt = clock.tick(60) / 1000.0
        fps = clock.get_fps()
        
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
            elif event.type == pygame.MOUSEMOTION:
                dx, dy = event.rel
                camera.process_mouse(dx, dy)
        
        # Handle keyboard input
        keys = pygame.key.get_pressed()
        camera.process_keyboard(keys, dt)
        
        # Clear screen
        glClearColor(0.53, 0.81, 0.92, 1.0)  # Sky blue
        glClear(int(GL_COLOR_BUFFER_BIT) | int(GL_DEPTH_BUFFER_BIT))
        
        # Use shader
        shader.use()
        
        # Set up matrices
        view_matrix = camera.get_view_matrix()
        proj_matrix = projection
        
        shader.set_mat4("model", model.flatten())
        shader.set_mat4("view", view_matrix.flatten())
        shader.set_mat4("projection", proj_matrix.flatten())
        
        # Lighting
        time_of_day = pygame.time.get_ticks() / 1000.0
        sun_angle = time_of_day * 0.05
        light_dir = np.array([math.sin(sun_angle), math.cos(sun_angle), 0.3], dtype=np.float32)
        shader.set_vec3("lightDir", light_dir)
        shader.set_vec3("viewPos", camera.position)
        shader.set_float("ambientStrength", 0.3)
        
        # Render chunks
        for chunk in chunks.values():
            chunk.render()
        
        # Swap buffers
        pygame.display.flip()
        pygame.display.set_caption(f"GPU Voxel World - FPS: {fps:.0f} | Pos: ({camera.position[0]:.1f}, {camera.position[1]:.1f}, {camera.position[2]:.1f})")
    
    # Cleanup
    pygame.quit()


if __name__ == "__main__":
    main()