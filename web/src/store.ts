import { configureStore } from "@reduxjs/toolkit";
import { useDispatch, useSelector } from "react-redux";

import { api } from "./api";
import { uiSlice } from "./uiSlice";

export function createStore() {
  return configureStore({
    reducer: {
      [api.reducerPath]: api.reducer,
      ui: uiSlice.reducer,
    },
    middleware: (getDefault) => getDefault().concat(api.middleware),
  });
}

export const store = createStore();

export type AppStore = ReturnType<typeof createStore>;
export type RootState = ReturnType<AppStore["getState"]>;
export type AppDispatch = AppStore["dispatch"];

export const useAppDispatch = useDispatch.withTypes<AppDispatch>();
export const useAppSelector = useSelector.withTypes<RootState>();
