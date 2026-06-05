#include "mesh_emu/app.h"
#include "mesh_emu/bridge.h"
#include "mesh_emu/log.h"

int mesh_emu_app_init(struct mesh_emu_app *app, const char *program_name)
{
    if (app == 0) {
        return 1;
    }

    app->program_name = program_name;
    mesh_emu_log_info("application initialized");
    return 0;
}

int mesh_emu_app_run(struct mesh_emu_app *app)
{
    struct mesh_emu_bridge bridge;

    if (app == 0) {
        return 1;
    }

    mesh_emu_bridge_init(&bridge);
    mesh_emu_log_info("starting single-Pi TCP-to-Bluetooth relay");
    return mesh_emu_bridge_start(&bridge);
}

void mesh_emu_app_shutdown(struct mesh_emu_app *app)
{
    if (app == 0) {
        return;
    }

    mesh_emu_log_info("application shutdown");
}
