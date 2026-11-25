with open("/root/builds/mesa-26.0.8/src/gallium/frontends/teflon/tfl_device.c", "r") as f:
    s = f.read()

old_create = """   if (delegate->dev == NULL) {
      fprintf(stderr, "Couldn't open kernel device\\n");
      return NULL;
   }

   teflon_debug("Teflon delegate: loaded %s driver\\n", delegate->dev->driver_name);

   screen = pipe_loader_create_screen(delegate->dev, false);
   delegate->context = screen->context_create(screen, NULL, PIPE_CONTEXT_COMPUTE_ONLY);

   return &delegate->base;"""

new_create = """   if (delegate->dev == NULL) {
      fprintf(stderr, "Couldn't open kernel device\\n");
      free(delegate);
      return NULL;
   }

   teflon_debug("Teflon delegate: loaded %s driver\\n", delegate->dev->driver_name);

   screen = pipe_loader_create_screen(delegate->dev, false);
   if (screen == NULL) {
      fprintf(stderr, "Couldn't create pipe screen\\n");
      pipe_loader_release(&delegate->dev, 1);
      free(delegate);
      return NULL;
   }

   delegate->context = screen->context_create(screen, NULL, PIPE_CONTEXT_COMPUTE_ONLY);
   if (delegate->context == NULL) {
      fprintf(stderr, "Couldn't create pipe context\\n");
      screen->destroy(screen);
      pipe_loader_release(&delegate->dev, 1);
      free(delegate);
      return NULL;
   }

   return &delegate->base;"""

old_destroy = """   screen = delegate->context->screen;
   delegate->context->destroy(delegate->context);
   screen->destroy(screen);
   pipe_loader_release(&delegate->dev, 1);
   free(delegate);"""

new_destroy = """   if (delegate->context != NULL) {
      screen = delegate->context->screen;
      delegate->context->destroy(delegate->context);
      if (screen != NULL)
         screen->destroy(screen);
   }
   if (delegate->dev != NULL)
      pipe_loader_release(&delegate->dev, 1);
   free(delegate);"""

assert old_create in s, "old_create not found"
s = s.replace(old_create, new_create, 1)

assert old_destroy in s, "old_destroy not found"
s = s.replace(old_destroy, new_destroy, 1)

with open("/root/builds/mesa-26.0.8/src/gallium/frontends/teflon/tfl_device.c", "w") as f:
    f.write(s)

print("tfl_device.c patched successfully")
