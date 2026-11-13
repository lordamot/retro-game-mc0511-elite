// Physical UKNC connector layouts. Canonical decoder table is YRGB.
#pragma once
#include <stdint.h>
#include <string.h>
enum class PaletteLayout { GRB, RGB };
static PaletteLayout g_paletteLayout = PaletteLayout::GRB;
static bool SetPaletteLayout(const char *name)
{
    if (!strcmp(name, "grb")) g_paletteLayout = PaletteLayout::GRB;
    else if (!strcmp(name, "rgb")) g_paletteLayout = PaletteLayout::RGB;
    else return false;
    return true;
}
static uint32_t PhysicalColor(uint32_t rgb)
{
    if (g_paletteLayout == PaletteLayout::RGB) return rgb;
    return (rgb & 0xff0000ffu) | ((rgb & 0x00ff0000u) >> 8)
         | ((rgb & 0x0000ff00u) << 8);
}
