AM_CPPFLAGS = -I$(top_srcdir)/include
AM_CFLAGS = -std=c89 -Wall -Wextra -Wpedantic

bin_PROGRAMS = mesh-emu

mesh_emu_LDADD = -lbluetooth

mesh_emu_SOURCES = \
	main.c \
	app.c \
	bridge.c \
	log.c
