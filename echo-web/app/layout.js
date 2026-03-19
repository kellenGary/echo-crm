import { Inter } from 'next/font/google';
import './globals.css';
import { MiniSidebar } from './components/MiniSidebar';

const inter = Inter({ subsets: ['latin'] });

export const metadata = {
  title: 'Echo CRM | Intelligence Platform',
  description: 'High-density intelligence exploration for Beeper conversations.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-background text-foreground antialiased`}>
        <div className="flex h-screen overflow-hidden">
          <MiniSidebar />
          <div className="flex-1 min-h-0 overflow-y-auto">
            {children}
          </div>
        </div>
      </body>
    </html>
  );
}
