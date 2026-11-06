// @svg-maps/india ships no type declarations. Its default export is the map:
// a viewBox and one path per state or union territory.
declare module "@svg-maps/india" {
  const india: {
    label: string;
    viewBox: string;
    locations: { id: string; name: string; path: string }[];
  };
  export default india;
}
