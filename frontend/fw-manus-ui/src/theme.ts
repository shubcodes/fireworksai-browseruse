import { createTheme, alpha } from '@mui/material/styles';

// Create a dark theme based on Apple's design guidelines
const theme = createTheme({
    palette: {
        mode: 'dark',
        primary: {
            main: '#0A84FF', // Apple iOS blue
            light: '#5AC8FA',
            dark: '#0055CC',
            contrastText: '#FFFFFF',
        },
        secondary: {
            main: '#64D2FF', // Apple macOS accent blue
            light: '#8FE5FF',
            dark: '#30A5C8',
            contrastText: '#000000',
        },
        background: {
            default: '#1C1C1E', // Apple dark mode background
            paper: '#2C2C2E', // Apple dark mode card background
        },
        text: {
            primary: '#FFFFFF',
            secondary: 'rgba(255, 255, 255, 0.7)',
            disabled: 'rgba(255, 255, 255, 0.5)',
        },
        divider: 'rgba(255, 255, 255, 0.12)',
        error: {
            main: '#FF453A', // Apple red
        },
        warning: {
            main: '#FF9F0A', // Apple orange
        },
        info: {
            main: '#64D2FF', // Apple blue
        },
        success: {
            main: '#30D158', // Apple green
        },
    },
    typography: {
        fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Icons", "Helvetica Neue", Helvetica, Arial, sans-serif',
        h1: {
            fontWeight: 700,
        },
        h2: {
            fontWeight: 700,
        },
        h3: {
            fontWeight: 600,
        },
        h4: {
            fontWeight: 600,
        },
        h5: {
            fontWeight: 600,
        },
        h6: {
            fontWeight: 500,
        },
        button: {
            textTransform: 'none',
            fontWeight: 500,
        },
    },
    components: {
        MuiAppBar: {
            styleOverrides: {
                root: {
                    backgroundColor: alpha('#1C1C1E', 0.7),
                    backdropFilter: 'blur(10px)',
                    boxShadow: '0 1px 0 0 rgba(255, 255, 255, 0.1)',
                },
            },
        },
        MuiButton: {
            styleOverrides: {
                root: {
                    borderRadius: 8,
                    textTransform: 'none',
                    padding: '8px 16px',
                },
                containedPrimary: {
                    background: 'linear-gradient(145deg, #0A84FF, #0055CC)',
                    '&:hover': {
                        background: 'linear-gradient(145deg, #0065CC, #003F99)',
                    },
                },
            },
        },
        MuiPaper: {
            styleOverrides: {
                root: {
                    backgroundImage: 'none',
                    borderRadius: 12,
                },
            },
        },
        MuiTab: {
            styleOverrides: {
                root: {
                    textTransform: 'none',
                    fontWeight: 500,
                },
            },
        },
        MuiDivider: {
            styleOverrides: {
                root: {
                    borderColor: 'rgba(255, 255, 255, 0.12)',
                },
            },
        },
        MuiTextField: {
            styleOverrides: {
                root: {
                    '& .MuiOutlinedInput-root': {
                        borderRadius: 8,
                    },
                },
            },
        },
    },
    shape: {
        borderRadius: 12,
    },
    shadows: [
        'none',
        '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
        '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
        '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
        '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
        '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
        '0 35px 60px -15px rgba(0, 0, 0, 0.3)',
        '0 45px 65px -15px rgba(0, 0, 0, 0.3)',
        '0 50px 80px -20px rgba(0, 0, 0, 0.4)',
        '0 65px 90px -30px rgba(0, 0, 0, 0.5)',
        '0 75px 100px -40px rgba(0, 0, 0, 0.6)',
        '0 80px 110px -40px rgba(0, 0, 0, 0.7)',
        '0 85px 120px -40px rgba(0, 0, 0, 0.8)',
        '0 90px 130px -40px rgba(0, 0, 0, 0.8)',
        '0 95px 140px -40px rgba(0, 0, 0, 0.9)',
        '0 100px 150px -40px rgba(0, 0, 0, 0.9)',
        '0 105px 160px -40px rgba(0, 0, 0, 1)',
        '0 110px 170px -40px rgba(0, 0, 0, 1)',
        '0 115px 180px -40px rgba(0, 0, 0, 1)',
        '0 120px 190px -40px rgba(0, 0, 0, 1)',
        '0 125px 200px -40px rgba(0, 0, 0, 1)',
        '0 130px 210px -40px rgba(0, 0, 0, 1)',
        '0 135px 220px -40px rgba(0, 0, 0, 1)',
        '0 140px 230px -40px rgba(0, 0, 0, 1)',
        '0 145px 240px -40px rgba(0, 0, 0, 1)',
    ],
});

export default theme;
