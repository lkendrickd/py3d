"""
Main entry point for the 3D voxel world - FIXED VERSION.
"""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
import pygame
import numpy as np
import ctypes
import math
import logging

from OpenGL.GL import (
    GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, GL_CULL_FACE,
    GL_BACK, GL_CCW, GL_TRIANGLES, glEnable, glCullFace, glFrontFace,
    glClearColor, glClear, glDrawArrays, glBindVertexArray
)

from config.settings import *
from engine.shader import Shader
from engine.camera import Camera
from engine.math_utils import perspective
from world.world_manager import WorldManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def main():
    logging.info("Starting main function.")
    # Initialize Pygame
    pygame.init()
    logging.info("Pygame initialized.")
    
    # Auto-detect native resolution
    try:
        info = pygame.display.Info()
        WINDOW_WIDTH = info.current_w
        WINDOW_HEIGHT = info.current_h
        logging.info(f"Detected native resolution: {WINDOW_WIDTH}x{WINDOW_HEIGHT}")
    except pygame.error as e:
        logging.error(f"Could not get display info: {e}. Using default resolution.")
        WINDOW_WIDTH, WINDOW_HEIGHT = 1280, 720

    # Set OpenGL attributes before creating the display
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_COMPATIBILITY)
    pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)
    pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
    pygame.display.gl_set_attribute(pygame.GL_SWAP_CONTROL, 1)  # Enable VSync
    logging.info("OpenGL attributes set.")
    
    # Set up display
    try:
        pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.DOUBLEBUF | pygame.OPENGL)
        logging.info("Display mode set.")
    except pygame.error as e:
        logging.error(f"Failed to set display mode: {e}")
        return

    pygame.display.set_caption("GPU Voxel World")
    logging.info("Display caption set.")
    
    # Lock cursor to window
    try:
        pygame.mouse.set_visible(False)
        pygame.event.set_grab(True)
        logging.info("Mouse grab set.")
    except pygame.error as e:
        logging.warning(f"Could not set mouse grab: {e}")

    # Enable depth testing and face culling
    try:
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glCullFace(GL_BACK)
        glClearColor(0.53, 0.81, 0.92, 1.0)  # Sky blue
        logging.info("OpenGL settings enabled.")
    except Exception as e:
        logging.error(f"Error setting OpenGL options: {e}")
        return
    
    # Create shader program
    try:
        shader = Shader(VERTEX_SHADER, FRAGMENT_SHADER)
        logging.info("Shader created.")
    except Exception as e:
        logging.error(f"Error creating shader: {e}")
        return

    # Create camera
    camera = Camera()
    logging.info("Camera created.")
    
    # Create world manager for dynamic chunk loading
    world_manager = WorldManager()
    logging.info("WorldManager created.")
    
    # Load initial chunks around spawn point (small area first)
    logging.info("Generating initial world...")
    initial_chunks = world_manager.load_initial_chunks(camera.position)
    logging.info(f"Initial world generated: {initial_chunks} chunks")
    
    # Matrices
    model = np.eye(4, dtype=np.float32)
    projection = perspective(math.radians(60), WINDOW_WIDTH / WINDOW_HEIGHT, 0.1, 1000.0)
    logging.info("Matrices created.")
    
    # Main loop
    clock = pygame.time.Clock()
    running = True
    frame_count = 0
    fps_history = []
    target_fps = 60
    
    # FIX: Track performance metrics
    low_fps_counter = 0
    last_chunk_count = 0

    logging.info("Entering main loop.")
    while running:
        dt = clock.tick(target_fps) / 1000.0
        fps = clock.get_fps()
        frame_count += 1
        
        # Track FPS for adaptive performance
        fps_history.append(fps)
        if len(fps_history) > 60:  # Keep last 60 frames
            fps_history.pop(0)
        
        avg_fps = sum(fps_history) / len(fps_history) if fps_history else 60
        
        # FIX: Track low FPS occurrences
        if fps < 30:
            low_fps_counter += 1
        else:
            low_fps_counter = max(0, low_fps_counter - 1)

        # Handle events
        try:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    # FIX: Add debug key to show stats
                    elif event.key == pygame.K_F3:
                        logging.info(f"\n=== Debug Stats ===")
                        logging.info(f"Chunks loaded: {len(world_manager.chunks)}")
                        logging.info(f"Chunks generating: {len(world_manager.generating_chunks)}")
                        logging.info(f"Mesh build queue: {world_manager.chunks_to_build_mesh.qsize()}")
                        logging.info(f"Cleanup queue: {len(world_manager.chunks_to_cleanup)}")
                        logging.info(f"FPS: {fps:.1f} (avg: {avg_fps:.1f})")
                        logging.info(f"Camera pos: {camera.position}")
                        logging.info(f"Camera dir: {camera.front}")
                        logging.info("==================\n")
                elif event.type == pygame.MOUSEMOTION:
                    dx, dy = event.rel
                    camera.process_mouse(dx, dy)
        except pygame.error as e:
            logging.warning(f"Pygame event error: {e}")


        # Handle keyboard input
        keys = pygame.key.get_pressed()
        camera.process_keyboard(keys, dt)
        
        # FIX: Adaptive update frequency based on performance and chunk status
        update_interval = 10
        if low_fps_counter > 10: update_interval = 30
        elif avg_fps < 45: update_interval = 20
        elif avg_fps > 55: update_interval = 5
        
        if frame_count % update_interval == 0:
            world_manager.update(camera.position, camera.front)
        
        # Clear screen
        glClear(int(GL_COLOR_BUFFER_BIT) | int(GL_DEPTH_BUFFER_BIT))
        
        # Use shader
        shader.use()
        
        # Set up matrices
        view_matrix = camera.get_view_matrix()
        shader.set_mat4("view", view_matrix.flatten())
        shader.set_mat4("projection", projection.flatten())
        
        # Render visible chunks
        visible_chunks = world_manager.get_visible_chunks(camera.position)
        for chunk in visible_chunks:
            chunk.render()

        # Swap buffers
        pygame.display.flip()

    logging.info("Exited main loop.")
    
    # Cleanup
    logging.info("Shutting down...")
    world_manager.cleanup()
    pygame.quit()
    logging.info("Shutdown complete.")


if __name__ == "__main__":
    main()