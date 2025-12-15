"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {cn} from "@forge/lib/utils"
import { Bell, Circle, Cpu, Menu, Settings } from "lucide-react";
import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuList,
} from "@forge/ui/components/ui/navigation-menu";


import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@forge/ui/components/ui/dropdown-menu";

import { Button } from "@forge/ui/components/ui/button";
import { useTelemetry } from "@forge/hooks/useTelemetry";

export default function TopNav() {
  const path = usePathname();
  const { latest, lastUpdate } = useTelemetry("edge1");

  const isLive = lastUpdate && Date.now() - lastUpdate < 3000;

  const navItems = [
    { href: "/machines/edge1", label: "Dashboard" },
    { href: "/machines/edge1/forecast", label: "Forecast" },
    { href: "/machines/edge1/workflow", label: "Workflow" },
    { href: "/machines/edge1/commands", label: "Commands" },
    { href: "/machines/edge1/video-ai", label: "Video AI" },
  ];

  return (
    <header className="fixed top-0  left-0 w-full h-24 z-50 border-b backdrop-blur-md">
      <div className="flex items-center justify-between h-16 px-4">
        
        {/* LEFT: LOGO + PRIMARY LINKS */}
        <div className="flex items-center gap-6">

          {/* LOGO */}
          <Link href="/" className="text-xl font-semibold">
            ForgePanel
          </Link>

          {/* NAVIGATION */}
          <NavigationMenu>
            <NavigationMenuList>
              {navItems.map((n) => (
                <NavigationMenuItem key={n.href}>
                  <Link
                    href={n.href}
                    className={cn(
                      "px-3 py-2 rounded-md text-sm font-medium hover:bg-accent",
                      path === n.href && "bg-accent text-primary"
                    )}
                  >
                    {n.label}
                  </Link>
                </NavigationMenuItem>
              ))}
            </NavigationMenuList>
          </NavigationMenu>
        </div>

        {/* RIGHT: STATUS + ALERTS + USER MENU */}
        <div className="flex items-center gap-4">
          
          {/* DEVICE STATUS */}
          <div className="flex items-center gap-2">
            <Circle
              className={cn(
                "h-3 w-3",
                isLive ? "text-green-500" : "text-red-500"
              )}
              fill={isLive ? "green" : "red"}
            />
            <span className="text-xs">
              {isLive ? "LIVE" : "OFFLINE"}
            </span>
          </div>

          {/* ALERTS */}
          <Button size="icon" variant="ghost">
            <Bell className="h-5 w-5" />
          </Button>

          {/* USER / SETTINGS */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="icon" variant="outline">
                <Settings className="h-5 w-5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem asChild>
                <Link href="/settings">Settings</Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/machines">Switch Machine</Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* MOBILE MENU (optional) */}
          <Button size="icon" variant="ghost" className="lg:hidden">
            <Menu className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </header>
  );
}
