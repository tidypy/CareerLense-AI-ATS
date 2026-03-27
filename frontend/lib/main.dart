import 'dart:convert';
import 'dart:ui';
import 'package:flutter/foundation.dart'; // For kIsWeb and typed_data indirectly
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:file_saver/file_saver.dart';
import 'package:universal_html/html.dart' as html;

void main() {
  runApp(const CareerLensApp());
}

class CareerLensApp extends StatelessWidget {
  const CareerLensApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CareerLens AI',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6750A4), // Primary purple
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        fontFamily: 'Roboto',
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFD0BCFF), // Light purple for dark mode
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
        fontFamily: 'Roboto',
      ),
      themeMode: ThemeMode.system,
      home: const CareerLensHome(),
    );
  }
}

class CareerLensHome extends StatefulWidget {
  const CareerLensHome({super.key});

  @override
  State<CareerLensHome> createState() => _CareerLensHomeState();
}

class _CareerLensHomeState extends State<CareerLensHome> with SingleTickerProviderStateMixin {
  final TextEditingController _resumeController = TextEditingController();
  final TextEditingController _jobDescController = TextEditingController();
  final TextEditingController _apiKeyController = TextEditingController();
  
  String _selectedSeniority = 'Mid-Level';
  final List<String> _seniorityOptions = ['Executive', 'Senior', 'Mid-Level', 'Junior', 'Entry'];
  
  bool _isLoading = false;
  String? _generatedHtml;
  String _apiStatus = "Checking API...";
  bool _isLocalFallback = false;

  static const String _resumePrefKey = "saved_master_resume";
  static const String _apiPrefKey = "saved_api_key";
  
  String get _backendUrl {
    if (kIsWeb) {
      return "${Uri.base.origin}/api/v1";
    } else if (defaultTargetPlatform == TargetPlatform.android) {
      return "http://10.0.2.2:8000/api/v1";
    }
    return "http://127.0.0.1:8000/api/v1";
  }

  // Animation controller for soft UI effects
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this, 
      duration: const Duration(milliseconds: 800)
    );
    _fadeAnimation = CurvedAnimation(
      parent: _animationController, 
      curve: Curves.decelerate
    );
    _animationController.forward();
    
    _loadSavedResume();
    _checkApiHealth();
    
    // Add listener for real-time key verification
    _apiKeyController.addListener(() {
      final key = _apiKeyController.text;
      // Debounce simple verification
      Future.delayed(const Duration(milliseconds: 500), () {
        if (key == _apiKeyController.text && mounted) {
          _verifyUserKey(key);
        }
      });
    });
    
    print("CareerLens Build Loaded: v1.0.1+2");
  }

  @override
  void dispose() {
    _animationController.dispose();
    _resumeController.dispose();
    _jobDescController.dispose();
    _apiKeyController.dispose();
    super.dispose();
  }

  Future<void> _loadSavedResume() async {
    final prefs = await SharedPreferences.getInstance();
    final savedResume = prefs.getString(_resumePrefKey);
    final savedApiKey = prefs.getString(_apiPrefKey);
    
    setState(() {
      if (savedResume != null && savedResume.isNotEmpty) _resumeController.text = savedResume;
      if (savedApiKey != null && savedApiKey.isNotEmpty) _apiKeyController.text = savedApiKey;
    });
  }

  Future<void> _saveResume(String resumeText) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_resumePrefKey, resumeText);
    await prefs.setString(_apiPrefKey, _apiKeyController.text.trim());
  }

  Future<void> _checkApiHealth() async {
    String healthUrl = "$_backendUrl/health";

    try {
      final response = await http.get(Uri.parse(healthUrl)).timeout(const Duration(seconds: 3));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        setState(() {
          _apiStatus = data['api_status'] ?? "API Connected";
        });
      } else {
        setState(() {
          _apiStatus = "API Error: ${response.statusCode}";
        });
      }
    } catch (e) {
      setState(() {
        _apiStatus = "API Offline";
      });
    }
  }

  Future<void> _verifyUserKey(String key) async {
    if (key.trim().isEmpty) {
      _checkApiHealth(); // Revert to server health check
      return;
    }

    setState(() {
      _apiStatus = "Verifying Key...";
    });

    try {
      final response = await http.post(
        Uri.parse("$_backendUrl/verify-key"),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'user_api_key': key.trim()}),
      ).timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final status = data['status'];
        setState(() {
          if (status == 'ok') {
            _apiStatus = "API Connected";
            _isLocalFallback = false;
          } else {
            _apiStatus = status;
            if (status.toString().contains("Offline")) {
              _isLocalFallback = true;
            }
          }
        });
      } else {
        setState(() {
          _apiStatus = "Verify Failed";
        });
      }
    } catch (e) {
      setState(() {
        _apiStatus = "Network Error";
      });
    }
  }

  Future<void> _generateCareerData() async {
    if (_jobDescController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Please provide a Job Description'),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      );
      return;
    }

    setState(() {
      _isLoading = true;
      _generatedHtml = null;
    });

    await _saveResume(_resumeController.text);

    String generateUrl = "$_backendUrl/generate";

    try {
      final response = await http.post(
        Uri.parse(generateUrl),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'job_description': _jobDescController.text.trim(),
          'master_resume': _resumeController.text.trim(),
          'target_seniority': _selectedSeniority,
          if (_apiKeyController.text.trim().isNotEmpty) 'user_api_key': _apiKeyController.text.trim(),
        }),
      );

      if (response.statusCode == 200) {
        // Check if the backend signalled a BYOK key failure + local fallback
        final byokError = response.headers['x-byok-error'];
        if (byokError != null && byokError.isNotEmpty && mounted) {
          setState(() {
            _isLocalFallback = true;
          });
          // Show blocking dialog — does NOT auto-dismiss
          await _showByokErrorDialog(byokError);
        }

        setState(() {
          _generatedHtml = response.body;
        });

        if (mounted) {
          final snackText = (byokError != null && byokError.isNotEmpty)
              ? 'Generated via Local RTX (key was invalid \u2014 see dismissed dialog)'
              : 'Template Successfully Generated!';
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(snackText),
              behavior: SnackBarBehavior.floating,
              backgroundColor: Theme.of(context).colorScheme.primary,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          );
        }
      } else {
        if (mounted) {
          String errorMessage = 'Generation Failed: \${response.statusCode}';
          try {
            final errorJson = jsonDecode(response.body);
            if (errorJson['detail'] != null) {
              errorMessage = errorJson['detail'].toString();
            }
          } catch (_) {
            errorMessage += ' - \${response.body}';
          }
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(errorMessage),
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error: \$e'),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  /// Shows a blocking modal dialog that the user MUST dismiss.
  /// Used when the user's BYOK key fails — the result was still generated
  /// via the Local RTX fallback, but the user needs to know their key is invalid.
  Future<void> _showByokErrorDialog(String reason) async {
    if (!mounted) return;
    return showDialog<void>(
      context: context,
      barrierDismissible: false, // User MUST tap OK — dialog does not auto-close
      builder: (BuildContext dialogContext) {
        final theme = Theme.of(dialogContext);
        final bool isQuotaExhausted = reason.toLowerCase().contains("quota") || reason.toLowerCase().contains("credits");
        
        return AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          backgroundColor: theme.colorScheme.errorContainer,
          icon: Icon(
            Icons.error_outline_rounded,
            color: theme.colorScheme.error,
            size: 48,
          ),
          title: Text(
            isQuotaExhausted ? '⌛ Quota Exhausted' : '⚠️ API Key Failed',
            style: TextStyle(
              color: theme.colorScheme.onErrorContainer,
              fontWeight: FontWeight.bold,
              fontSize: 22,
            ),
            textAlign: TextAlign.center,
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                reason,
                style: TextStyle(
                  color: theme.colorScheme.onErrorContainer,
                  fontSize: 15,
                  height: 1.6,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: Colors.orange.withAlpha(40),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.orange.withAlpha(100), width: 1),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.auto_awesome, color: Colors.orange, size: 20),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'Automatic Fallback: Your profile was generated using the Local RTX LLM.',
                        style: TextStyle(
                          color: theme.colorScheme.onErrorContainer,
                          fontWeight: FontWeight.bold,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          actionsAlignment: MainAxisAlignment.center,
          actions: [
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: theme.colorScheme.error,
                  foregroundColor: theme.colorScheme.onError,
                  elevation: 0,
                  padding: const EdgeInsets.symmetric(horizontal: 48, vertical: 16),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                ),
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: const Text('CONTINUE TO RESULT', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1.1)),
              ),
            ),
          ],
        );
      },
    );
  }

  Future<void> _downloadHtml() async {
    if (_generatedHtml == null) return;
    try {
      // Dynamically extract the job title from the generated HTML
      String jobTitleString = '';
      final RegExp regExp = RegExp(r'Target Role.*?<h1[^>]*>(.*?)</h1>', dotAll: true, caseSensitive: false);
      final match = regExp.firstMatch(_generatedHtml!);
      
      if (match != null && match.group(1) != null) {
        String rawTitle = match.group(1)!;
        // Strip out any accidental inner HTML tags and keep only letters, numbers, and spaces
        rawTitle = rawTitle.replaceAll(RegExp(r'<[^>]*>'), '');
        rawTitle = rawTitle.replaceAll(RegExp(r'[^a-zA-Z0-9 ]'), '').trim();
        
        if (rawTitle.isNotEmpty) {
          jobTitleString = '${rawTitle.replaceAll(' ', '_')}_';
        }
      }

      final bytes = Uint8List.fromList(utf8.encode(_generatedHtml!));
      final filename = 'CareerLens_Report_$jobTitleString\${DateTime.now().millisecondsSinceEpoch}.html';

      if (kIsWeb) {
        final blob = html.Blob([bytes], 'text/html');
        final url = html.Url.createObjectUrlFromBlob(blob);
        html.AnchorElement(href: url)
          ..setAttribute("download", filename)
          ..click();
        html.Url.revokeObjectUrl(url);
      } else {
        await FileSaver.instance.saveFile(
          name: 'CareerLens_Report_$jobTitleString\${DateTime.now().millisecondsSinceEpoch}',
          bytes: bytes,
          fileExtension: 'html',
          mimeType: MimeType.custom,
          customMimeType: 'text/html',
        );
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('HTML file saved successfully!'),
            backgroundColor: Theme.of(context).colorScheme.primary,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error saving file: \$e'),
            backgroundColor: Theme.of(context).colorScheme.error,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDesktopOrWeb = MediaQuery.of(context).size.width > 800;

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('CareerLens AI', style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 1.2)),
        centerTitle: true,
        elevation: 0,
        backgroundColor: Colors.transparent,
        flexibleSpace: ClipRRect(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
            child: Container(
              color: theme.colorScheme.surface.withAlpha(150),
            ),
          ),
        ),
        actions: [
          Center(
            child: Padding(
              padding: const EdgeInsets.only(right: 16.0),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 500),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: _isLocalFallback 
                      ? Colors.orange.withAlpha(200)
                      : (_apiStatus.contains('Connected') 
                          ? theme.colorScheme.primaryContainer.withAlpha(200)
                          : theme.colorScheme.errorContainer.withAlpha(200)),
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: [
                    if (_isLocalFallback) 
                      BoxShadow(
                        color: Colors.orange.withAlpha(80),
                        blurRadius: 12,
                        spreadRadius: 2,
                      ),
                  ],
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      _isLocalFallback 
                          ? Icons.warning_amber_rounded 
                          : (_apiStatus.contains('Connected') ? Icons.check_circle : Icons.error),
                      size: 16,
                      color: _isLocalFallback 
                          ? Colors.white 
                          : (_apiStatus.contains('Connected') 
                              ? theme.colorScheme.onPrimaryContainer 
                              : theme.colorScheme.onErrorContainer),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      _isLocalFallback ? "LOCAL FALLBACK" : _apiStatus.toUpperCase(),
                      style: TextStyle(
                        color: _isLocalFallback 
                            ? Colors.white 
                            : (_apiStatus.contains('Connected') 
                                ? theme.colorScheme.onPrimaryContainer 
                                : theme.colorScheme.onErrorContainer),
                        fontWeight: FontWeight.w900,
                        fontSize: 11,
                        letterSpacing: 0.8,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          )
        ],
      ),
      body: Stack(
        children: [
          // Blended Background
          Positioned.fill(
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    theme.colorScheme.primaryContainer.withAlpha(100),
                    theme.colorScheme.tertiaryContainer.withAlpha(100),
                    theme.colorScheme.surface,
                  ],
                  stops: const [0.0, 0.5, 1.0],
                ),
              ),
            ),
          ),
          
          // Decorative background circles for more blend effect
          Positioned(
            top: -100,
            right: -100,
            child: Container(
              width: 300,
              height: 300,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: theme.colorScheme.secondary.withAlpha(30),
              ),
            ),
          ),
          Positioned(
            bottom: -50,
            left: -50,
            child: Container(
              width: 250,
              height: 250,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: theme.colorScheme.primary.withAlpha(30),
              ),
            ),
          ),

          SafeArea(
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: isDesktopOrWeb 
                ? _buildWideLayout(theme) 
                : _buildNarrowLayout(theme),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWideLayout(ThemeData theme) {
    return Padding(
      padding: const EdgeInsets.all(24.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            flex: 1,
            child: CareerLensGlassCard(
              child: _buildInputSection(theme),
            ),
          ),
          const SizedBox(width: 24),
          Expanded(
            flex: 1,
            child: CareerLensGlassCard(
              child: _generatedHtml != null 
                  ? _buildOutputSection(theme) 
                  : _buildAdPlaceholder(theme),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNarrowLayout(ThemeData theme) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CareerLensGlassCard(
            child: _buildInputSection(theme),
          ),
          const SizedBox(height: 24),
          CareerLensGlassCard(
            child: _generatedHtml != null 
                ? _buildOutputSection(theme) 
                : _buildAdPlaceholder(theme),
          ),
        ],
      ),
    );
  }

  Widget _buildInputSection(ThemeData theme) {
    return Padding(
      padding: const EdgeInsets.all(24.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Input Details',
            style: theme.textTheme.headlineSmall?.copyWith(
              fontWeight: FontWeight.w800, 
              color: theme.colorScheme.onSurface,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Provide your master resume and the target job description to generate a tailored profile.',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              height: 1.5,
            ),
          ),
          const SizedBox(height: 32),
          _buildSoftTextField(
            controller: _resumeController, 
            theme: theme, 
            label: 'Master Resume', 
            hint: 'Paste your full master resume here...', 
            maxLines: 8
          ),
          const SizedBox(height: 24),
          _buildSoftTextField(
            controller: _jobDescController, 
            theme: theme, 
            label: 'Job Description', 
            hint: 'Paste the target job description here...', 
            maxLines: 6
          ),
          const SizedBox(height: 24),
          _buildSeniorityDropdown(theme),
          const SizedBox(height: 24),
          _buildSoftTextField(
            controller: _apiKeyController, 
            theme: theme, 
            label: 'API Key (Optional — blank uses Local RTX)', 
            hint: 'Leave blank to use Local RTX, or paste a Google Gemini API key...', 
            maxLines: 1
          ),
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity,
            height: 56,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                boxShadow: [
                  BoxShadow(
                    color: _isLoading 
                        ? Colors.transparent 
                        : theme.colorScheme.primary.withAlpha(80),
                    blurRadius: 12,
                    offset: const Offset(0, 6),
                  )
                ]
              ),
              child: ElevatedButton.icon(
                onPressed: _isLoading ? null : _generateCareerData,
                style: ElevatedButton.styleFrom(
                  backgroundColor: theme.colorScheme.primary,
                  foregroundColor: theme.colorScheme.onPrimary,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                  elevation: 0, // Handled by AnimatedContainer box shadow for softer look
                ),
                icon: _isLoading 
                    ? const SizedBox(
                        width: 24, 
                        height: 24, 
                        child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2)
                      )
                    : const Icon(Icons.auto_awesome),
                label: Text(
                  _isLoading ? 'Generating Data...' : 'Generate Tailored Profile', 
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, letterSpacing: 0.5)
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSoftTextField({
    required TextEditingController controller,
    required ThemeData theme,
    required String label,
    required String hint,
    required int maxLines,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface.withAlpha(150),
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: theme.colorScheme.shadow.withAlpha(10),
            blurRadius: 8,
            offset: const Offset(0, 2),
            spreadRadius: 1,
          )
        ]
      ),
      child: TextField(
        controller: controller,
        maxLines: maxLines,
        style: TextStyle(color: theme.colorScheme.onSurface),
        decoration: InputDecoration(
          labelText: label,
          alignLabelWithHint: true,
          labelStyle: TextStyle(color: theme.colorScheme.primary),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide.none,
          ),
          filled: true,
          fillColor: Colors.transparent, // Color is handled by the Container
          hintText: hint,
          hintStyle: TextStyle(color: theme.colorScheme.onSurfaceVariant.withAlpha(100)),
          contentPadding: const EdgeInsets.all(20),
        ),
      ),
    );
  }

  Widget _buildOutputSection(ThemeData theme) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(48),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.check_circle_outline, size: 80, color: theme.colorScheme.primary),
          const SizedBox(height: 24),
          Text(
            'Template Successfully Generated!',
            style: TextStyle(
              color: theme.colorScheme.onSurface,
              fontSize: 24,
              fontWeight: FontWeight.bold,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          Text(
            'Your ATS-optimized resume profile is ready.',
            style: TextStyle(
              color: theme.colorScheme.onSurfaceVariant,
              fontSize: 16,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 48),
          SizedBox(
            width: double.infinity,
            height: 64,
            child: ElevatedButton.icon(
              onPressed: _downloadHtml,
              style: ElevatedButton.styleFrom(
                backgroundColor: theme.colorScheme.primary,
                foregroundColor: theme.colorScheme.onPrimary,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                ),
                elevation: 4,
              ),
              icon: const Icon(Icons.download, size: 28),
              label: const Text(
                'SAVE AS HTML',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, letterSpacing: 1.5),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAdPlaceholder(ThemeData theme) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.campaign_outlined, size: 64, color: theme.colorScheme.outline.withAlpha(50)),
          const SizedBox(height: 16),
          Text(
            'Ad Space Available',
            style: TextStyle(
              color: theme.colorScheme.outline.withAlpha(150),
              fontSize: 18,
              fontWeight: FontWeight.w600,
              letterSpacing: 2,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSeniorityDropdown(ThemeData theme) {
    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface.withAlpha(150),
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: theme.colorScheme.shadow.withAlpha(10),
            blurRadius: 8,
            offset: const Offset(0, 2),
            spreadRadius: 1,
          )
        ]
      ),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
      child: DropdownButtonFormField<String>(
        value: _selectedSeniority,
        decoration: InputDecoration(
          labelText: 'Target Job Seniority Strategy',
          labelStyle: TextStyle(color: theme.colorScheme.primary, fontWeight: FontWeight.bold),
          border: InputBorder.none,
        ),
        dropdownColor: theme.colorScheme.surface,
        style: TextStyle(color: theme.colorScheme.onSurface, fontSize: 16),
        items: _seniorityOptions.map((String value) {
          return DropdownMenuItem<String>(
            value: value,
            child: Text(value),
          );
        }).toList(),
        onChanged: (newValue) {
          setState(() {
            _selectedSeniority = newValue!;
          });
        },
      ),
    );
  }
}

class CareerLensGlassCard extends StatelessWidget {
  final Widget child;

  const CareerLensGlassCard({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 16.0, sigmaY: 16.0),
        child: Container(
          decoration: BoxDecoration(
            color: theme.colorScheme.surface.withAlpha(140),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: theme.colorScheme.onSurface.withAlpha(20),
              width: 1.5,
            ),
            boxShadow: [
              BoxShadow(
                color: theme.colorScheme.shadow.withAlpha(15),
                blurRadius: 30,
                spreadRadius: -5,
                offset: const Offset(0, 10),
              )
            ]
          ),
          child: child,
        ),
      ),
    );
  }
}
