#include <stdio.h>
#include "mesh_emu/app.h"

int main(int argc, char **argv)
{
    struct mesh_emu_app app;
    int result;
    const char *program_name;

    program_name = (argc > 0 && argv[0] != 0) ? argv[0] : "mesh-emu";

    result = mesh_emu_app_init(&app, program_name);
    if (result != 0) {
        fprintf(stderr, "failed to initialize application\n");
        return result;
    }

    result = mesh_emu_app_run(&app);
    mesh_emu_app_shutdown(&app);
    return result;
}
