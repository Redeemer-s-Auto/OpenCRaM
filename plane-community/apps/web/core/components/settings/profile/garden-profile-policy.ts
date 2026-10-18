export function isGardenManagedProfileTab(gardenMode: boolean, tab: string): boolean {
  return gardenMode && (tab === "general" || tab === "security");
}
