#ifndef MESH_EMU_APP_H
#define MESH_EMU_APP_H

struct mesh_emu_app {
    const char *program_name;
};

int mesh_emu_app_init(struct mesh_emu_app *app, const char *program_name);
int mesh_emu_app_run(struct mesh_emu_app *app);
void mesh_emu_app_shutdown(struct mesh_emu_app *app);

#endif
