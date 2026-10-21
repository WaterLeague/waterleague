import { createContext, useContext } from 'react';

export const ServerConnectedContext = createContext(true);
export const useServerConnected = () => useContext(ServerConnectedContext);
